from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from jarvis.core.config import Settings

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
helper_spec = importlib.util.spec_from_file_location(
    "smoke_analysis", SCRIPTS / "smoke_analysis.py"
)
helper = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helper)
sys.modules.setdefault("smoke_analysis", helper)
spec = importlib.util.spec_from_file_location("smoke_isolation", SCRIPTS / "smoke_isolation.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class App:
    def __init__(self, fixture, failure):
        self.fixture = fixture
        self.failure = failure
        self.viewer = False
        self.revoked_once = False
        self.docs = {}
        self.analyses = {}
        self.logged_out = set()
        self.deleted = []
        self.calls = []

    def seed(self, index, document, digest):
        assert self.docs[document]["sha256"] == digest
        value = {"id": str(uuid4()), "document_id": document}
        self.analyses[document] = value
        return value["id"]

    def membership(self, *, grant):
        self.viewer = grant
        if not grant:
            self.revoked_once = True
            if self.failure == "stale_membership":
                self.viewer = True

    def request(self, method, route, token="", data=None, headers=None, *, timeout=15):
        def reply(code, value=None):
            return code, json.dumps(value).encode() if value is not None else b""

        self.calls.append((method, route))
        if route.endswith("/auth/login"):
            index = self.fixture.emails.index(json.loads(data)["email"])
            return reply(200, {"access_token": f"synthetic-{index}"})
        index = int(token.rsplit("-", 1)[1])
        if route.endswith("/auth/logout"):
            self.logged_out.add(index)
            return reply(204)
        if route == "/api/v1/me":
            return (
                reply(401)
                if index in self.logged_out
                else reply(200, {"id": str(self.fixture.users[index])})
            )
        parts = route.split("/")
        household = parts[4]
        owner = [str(value) for value in self.fixture.households].index(household)
        role = (
            "owner"
            if index == owner
            else ("viewer" if index == 1 and owner == 0 and self.viewer else None)
        )
        if role is None:
            if self.failure == "cross_leak" and method == "GET":
                return reply(200, {"private_fixture": True})
            return reply(404)
        if len(parts) == 6 and method == "POST":
            document = str(uuid4())
            value = {
                "id": document,
                "household_id": household,
                "original_filename": headers["X-Filename"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
            self.docs[document] = {**value, "content": data}
            return reply(201, value)
        document = parts[6]
        item = self.docs.get(document)
        if item is None:
            return reply(404)
        suffix = "/".join(parts[7:])
        if method == "GET" and suffix == "content":
            if self.revoked_once and self.failure == "cleanup_content":
                return 200, b"changed-content"
            return 200, item["content"]
        if role == "viewer" and method in {"POST", "DELETE"}:
            return reply(200 if self.failure == "viewer_write" else 403)
        if method == "DELETE":
            self.deleted.append(document)
            del self.docs[document]
            return reply(204)
        if suffix in {"analysis", "analysis/latest"}:
            analysis = self.analyses[document]
            if self.failure == "hash_cache_leak" and owner == 1:
                analysis = next(iter(self.analyses.values()))
            return reply(200, analysis)
        raise AssertionError("Unexpected mocked route")


@pytest.mark.parametrize(
    "failure",
    [None, "cross_leak", "viewer_write", "stale_membership", "hash_cache_leak", "cleanup_content"],
)
def test_two_identity_checks_detect_boundary_failures_and_guard_cleanup(
    monkeypatch, tmp_path, failure
):
    fixture = smoke.Fixture(Settings.from_environment({}))
    fixture.manifest = tmp_path / "fixture.json"
    app = App(fixture, failure)
    monkeypatch.setattr(fixture, "seed_analysis", app.seed)
    monkeypatch.setattr(fixture, "viewer", app.membership)
    monkeypatch.setattr(smoke, "request", app.request)
    monkeypatch.setattr(helper, "request", app.request)
    # call() resolves request in its original helper module.
    monkeypatch.setattr(sys.modules[smoke.call.__module__], "request", app.request)
    result = {}
    if failure is None:
        smoke.run(fixture, result)
        assert result["membership_revocation_effective_on_existing_session"]
        assert result["revoked_membership_session_still_authenticated"]
        assert result["identical_hash_cached_analyses_isolated"]
        assert result["synthetic_documents_removed_from_app"]
        assert set(app.deleted) == set(fixture.documents)
        assert app.logged_out == {0, 1}
    else:
        with pytest.raises(smoke.Failure):
            smoke.run(fixture, result)
        assert not app.deleted
    stored = fixture.manifest.read_text()
    assert all(value not in stored for value in fixture.passwords)


class Rows:
    def __init__(self, value):
        self.value = value

    def fetchall(self):
        return self.value


@pytest.mark.parametrize("changed", ["users", "households"])
def test_cleanup_refuses_changed_or_unrelated_fixture_identity(changed):
    fixture = smoke.Fixture(Settings.from_environment({}))
    mutations = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, statement, parameters):
            if statement.startswith("SELECT id, email"):
                values = list(zip(fixture.users, fixture.emails, strict=True))
                return Rows([] if changed == "users" else values)
            if statement.startswith("SELECT id, name"):
                return Rows([])
            mutations.append(statement)
            raise AssertionError("Mutation before validating fixture identities")

    fixture.connect = Connection
    with pytest.raises(smoke.Failure):
        fixture.deactivate()
    assert mutations == []


def test_failure_still_disables_only_fixture_accounts_and_redacts_output(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(sys, "argv", ["smoke_isolation.py"])
    fixture = smoke.Fixture(Settings.from_environment({}))
    fixture.manifest = tmp_path / "fixture.json"
    fixture.provisioned = True
    deactivated = []
    monkeypatch.setattr(fixture, "provision", lambda: None)
    monkeypatch.setattr(fixture, "deactivate", lambda: deactivated.append(tuple(fixture.users)))
    monkeypatch.setattr(smoke, "Fixture", lambda _: fixture)

    def fail(*args):
        raise TimeoutError("private error with credentials")

    monkeypatch.setattr(smoke, "run", fail)
    assert smoke.main() == 1
    output = capsys.readouterr().out
    result = json.loads(output.splitlines()[-1])
    assert result["test_accounts_disabled"] and result["test_sessions_revoked"]
    assert deactivated == [tuple(fixture.users)]
    assert fixture.passwords == []
    assert "private error" not in output


def test_recovery_only_does_not_provision_or_request_analysis(monkeypatch, capsys):
    run_id = uuid4().hex
    fixture = smoke.Fixture(Settings.from_environment({}))
    deactivated = []

    def locate(value):
        assert value == run_id
        fixture.run_id = value
        fixture.provisioned = True

    monkeypatch.setattr(sys, "argv", ["smoke_isolation.py", "--deactivate-run", run_id])
    monkeypatch.setattr(smoke, "Fixture", lambda _: fixture)
    monkeypatch.setattr(fixture, "locate_run", locate)
    monkeypatch.setattr(fixture, "deactivate", lambda: deactivated.append(True))
    monkeypatch.setattr(fixture, "provision", lambda: pytest.fail("Unexpected provisioning"))
    monkeypatch.setattr(smoke, "run", lambda *_: pytest.fail("Unexpected test run"))
    assert smoke.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["recovery_only"] and result["fixture_run_id"] == run_id
    assert result["test_accounts_disabled"] and deactivated == [True]


def test_recovery_rejects_non_fixture_identifier_before_connecting(monkeypatch):
    fixture = smoke.Fixture(Settings.from_environment({}))
    monkeypatch.setattr(fixture, "connect", lambda: pytest.fail("Unexpected database access"))
    with pytest.raises(ValueError):
        fixture.locate_run("a-real-user-email@example.invalid")
    assert fixture.provisioned is False
