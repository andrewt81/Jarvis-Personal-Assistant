from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jarvis import preflight
from jarvis.core.config import Settings


@pytest.fixture
def configured(tmp_path: Path):
    path = tmp_path / "password"
    path.write_text("synthetic-password", encoding="utf-8")
    return Settings.from_environment(
        {
            "JARVIS_DB_HOST": "db-app.invalid",
            "JARVIS_DB_NAME": "jarvis",
            "JARVIS_DB_USER": "jarvis_app",
            "JARVIS_DB_PASSWORD_FILE": str(path),
        }
    )


class Engine:
    def __init__(self):
        self.statements = []
        self.disposed = False
        self.row = {
            "database": "jarvis",
            "role": "jarvis_app",
            "tls": True,
            "schema_usage": True,
            "schema_create": True,
            "migrations_present": False,
        }

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def exec_driver_sql(self, statement):
        self.statements.append(str(statement))
        return self

    def mappings(self):
        return self

    def one(self):
        return self.row

    def dispose(self):
        self.disposed = True


def test_authenticated_database_check_is_read_only_and_verifies_tls(configured, monkeypatch):
    engine = Engine()
    monkeypatch.setattr(preflight, "_database_engine", lambda _: engine)
    result = preflight.check_postgresql(configured)
    assert engine.statements[0] == "SET TRANSACTION READ ONLY"
    assert engine.statements[1] == "SET LOCAL statement_timeout = '5s'"
    assert len(engine.statements) == 3
    assert engine.statements[2].startswith("SELECT ")
    assert result["configured_identity_verified"] and result["tls"]
    assert result["migrations_present"] is False
    assert engine.disposed


@pytest.mark.parametrize(
    "change",
    [
        {"database": "other"},
        {"role": "postgres"},
        {"tls": False},
    ],
)
def test_wrong_database_role_or_unencrypted_connection_fails(configured, monkeypatch, change):
    engine = Engine()
    engine.row.update(change)
    monkeypatch.setattr(preflight, "_database_engine", lambda _: engine)
    with pytest.raises(RuntimeError):
        preflight.check_postgresql(configured)
    assert engine.disposed


def test_disabled_tls_rejected_before_connecting(configured, monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Connection should not be attempted")

    monkeypatch.setattr(preflight, "_database_engine", unexpected)
    with pytest.raises(RuntimeError, match="TLS must be required"):
        preflight.check_postgresql(replace(configured, postgres_sslmode="disable"))


def test_check_runs_both_dependencies_and_redacts_errors(configured, monkeypatch):
    monkeypatch.setattr(preflight, "check_postgresql", lambda _: {"status": "available"})

    def unavailable(_):
        raise RuntimeError("synthetic-password and upstream private body")

    monkeypatch.setattr(preflight, "_head_bucket", unavailable)
    result = preflight.check_storage(configured)
    assert result["postgresql"]["status"] == "available"
    assert result["object_storage"] == {"status": "unavailable"}
    assert result["ok"] is False
    assert "synthetic-password" not in json.dumps(result)
    assert "private body" not in json.dumps(result)


def test_s3_success_does_not_claim_object_permissions(configured, monkeypatch):
    monkeypatch.setattr(preflight, "check_postgresql", lambda _: {"status": "available"})
    monkeypatch.setattr(preflight, "_head_bucket", lambda _: None)
    result = preflight.check_storage(configured)
    assert result["ok"] is True
    assert result["object_storage"]["head_bucket"] is True
    assert result["object_storage"]["object_read_write_permissions"] == "not_tested"


def test_invalid_environment_does_not_print_secrets(monkeypatch, capsys):
    monkeypatch.setenv("JARVIS_DB_PORT", "private-invalid-value")
    assert preflight.main() == 1
    output = capsys.readouterr().out
    assert "private-invalid-value" not in output
    assert json.loads(output)["error"] == "invalid_configuration"
