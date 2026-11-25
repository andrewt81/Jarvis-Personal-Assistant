from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from jarvis.core.config import Settings

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
for name in ("smoke_analysis", "smoke_isolation", "smoke_revisions"):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
smoke = sys.modules["smoke_revisions"]


class App:
    def __init__(self, fixture, failure):
        self.fixture, self.failure = fixture, failure
        self.docs = {}
        self.current = None
        self.old = None
        self.analyses = {}
        self.inference_calls = 0
        self.logged_out = set()
        self.lock = threading.Lock()

    def store(self, data, filename):
        doc_id = str(uuid4())
        value = {
            "id": doc_id,
            "household_id": str(self.fixture.households[0]),
            "original_filename": filename,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        self.docs[doc_id] = (value, data)
        self.current = doc_id
        return value

    def seed(self, index, doc_id, digest):
        assert index == 0 and self.docs[doc_id][0]["sha256"] == digest
        value = {"id": str(uuid4()), "document_id": doc_id, "source_sha256": digest}
        self.analyses[doc_id] = value
        return value["id"]

    def request(self, method, route, token="", data=None, headers=None, *, timeout=15):
        def reply(code, value=None):
            return code, json.dumps(value).encode() if value is not None else b""

        if route.endswith("/auth/login"):
            index = self.fixture.emails.index(json.loads(data)["email"])
            return reply(200, {"access_token": f"fixture-{index}"})
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
        if index == 1:
            return reply(200 if self.failure == "privacy" else 404)
        parts = route.split("/")
        if len(parts) == 6:
            if method == "POST":
                value = self.store(data, headers["X-Filename"])
                self.old = value["id"]
                return reply(201, value)
            return reply(200, [self.docs[self.current][0]])
        doc_id = parts[6]
        value, content = self.docs[doc_id]
        suffix = "/".join(parts[7:])
        if method == "DELETE":
            return reply(409)
        if suffix == "content":
            if self.failure == "original" and doc_id == self.old:
                return 200, b"changed-original"
            return 200, content
        if suffix == "revisions" and method == "POST":
            if not headers.get("If-Match"):
                return reply(428)
            if headers["If-Match"] != '"' + value["sha256"] + '"':
                return reply(412)
            with self.lock:
                if doc_id != self.current and self.failure != "fork":
                    return reply(409)
                created = self.store(data, headers["X-Filename"])
            return reply(200, created)
        if suffix == "revisions/current":
            return reply(200, self.docs[self.current][0])
        if suffix == "revisions":
            return reply(200, [item[0] for item in self.docs.values()])
        if doc_id != self.current:
            if self.failure == "stale_analysis":
                return reply(200, self.analyses[self.old])
            return reply(409)
        if suffix == "analysis/latest":
            if self.failure == "old_cache":
                return reply(200, self.analyses[self.old])
            return reply(200, self.analyses[doc_id]) if doc_id in self.analyses else reply(404)
        if suffix == "analysis":
            if doc_id not in self.analyses:
                assert timeout > 3600
                self.inference_calls += 1
                text = content.decode()
                marker = text.split("Codice pratica: ")[1].splitlines()[0]
                date = "5 dicembre 2026" if marker.endswith("-A") else "8 dicembre 2026"
                iso = "2026-12-05" if marker.endswith("-A") else "2026-12-08"
                if self.failure == "old_deadline":
                    iso, date = "2026-11-30", "30 novembre 2026"
                self.analyses[doc_id] = {
                    "id": str(uuid4()),
                    "document_id": doc_id,
                    "source_sha256": "wrong" if self.failure == "source_hash" else value["sha256"],
                    "facts": [{"source_text": marker}],
                    "deadlines": [{"date": iso, "source_text": date}],
                }
            return reply(200, self.analyses[doc_id])
        raise AssertionError("Unexpected mocked route")


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "fork",
        "original",
        "stale_analysis",
        "old_cache",
        "privacy",
        "source_hash",
        "old_deadline",
    ],
)
def test_revision_smoke_detects_stale_data_and_preserves_every_original(
    monkeypatch, tmp_path, failure
):
    fixture = smoke.Fixture(Settings.from_environment({}))
    fixture.manifest = tmp_path / "manifest.json"
    app = App(fixture, failure)
    monkeypatch.setattr(fixture, "seed_analysis", app.seed)
    monkeypatch.setattr(smoke, "request", app.request)
    monkeypatch.setitem(smoke.call.__globals__, "request", app.request)
    result = {}
    if failure is None:
        smoke.run(fixture, result)
        assert result["new_analysis_hash_marker_and_deadline_verified"]
        assert result["new_revision_analysis_persisted_and_cached"]
        assert app.logged_out == {0, 1} and app.inference_calls == 1
    else:
        with pytest.raises(smoke.Failure):
            smoke.run(fixture, result)
        assert app.inference_calls <= 1
    assert len(app.docs) >= 2
    assert all(password not in repr(result) for password in fixture.passwords)


def test_failure_deactivates_fixture_accounts_without_deleting_revisions(monkeypatch, capsys):
    fixture = smoke.Fixture(Settings.from_environment({"JARVIS_AI_PROVIDER": "openwebui"}))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, *_):
            return self

        def fetchall(self):
            return [("20261125_0007",)]

    deactivated = []

    def provision():
        fixture.provisioned = True

    def fail(*_):
        raise TimeoutError("private diagnostic")

    monkeypatch.setattr(smoke, "Fixture", lambda _: fixture)
    monkeypatch.setattr(fixture, "connect", Connection)
    monkeypatch.setattr(fixture, "provision", provision)
    monkeypatch.setattr(fixture, "deactivate", lambda: deactivated.append(True))
    monkeypatch.setattr(smoke, "run", fail)
    assert smoke.main() == 1
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["test_accounts_disabled"] and result["test_sessions_revoked"]
    assert result["original_retention_policy"] == "keep_for_diagnosis" and deactivated == [True]
    assert fixture.passwords == [] and "private diagnostic" not in repr(result)
