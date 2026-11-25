from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location(
    "smoke_analysis", Path(__file__).resolve().parents[2] / "scripts" / "smoke_analysis.py"
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class App:
    def __init__(self, failure):
        self.failure = failure
        self.household = str(uuid4())
        self.document = str(uuid4())
        self.analysis = None
        self.deleted = False
        self.logged_out = False
        self.content_reads = 0

    def request(self, method, route, token="", data=None, headers=None, *, timeout=15):
        def reply(code, value=None):
            return code, json.dumps(value).encode() if value is not None else b""

        if route.endswith("/auth/login"):
            return reply(200, {"access_token": "private-token"})
        if route.endswith("/auth/logout"):
            self.logged_out = True
            return reply(204)
        if route == "/api/v1/me":
            return reply(401)
        if route == "/api/v1/households":
            return reply(200, [{"id": self.household, "role": "owner"}])
        assert token == "private-token" or route.endswith(  # noqa: S105 - mock only
            ("/analysis", "/analysis/latest")
        )
        base = f"/api/v1/households/{self.household}/documents"
        own = base + "/" + self.document
        if route == base and method == "GET":
            return reply(200, [{"id": self.document}] if self.failure == "old_id" else [])
        if route == base and method == "POST":
            self.content = data
            if headers["Content-Type"] == "application/pdf":
                assert headers["X-Filename"].endswith(".pdf")
                assert data.startswith(b"%PDF-1.4")
            else:
                assert headers["Content-Type"] == "text/plain"
                assert headers["X-Filename"].endswith(".txt")
            return reply(
                201,
                {
                    "id": self.document,
                    "household_id": self.household,
                    "original_filename": headers["X-Filename"],
                    "sha256": "wrong"
                    if self.failure == "bad_metadata"
                    else hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                },
            )
        if route == own + "/content":
            self.content_reads += 1
            if self.deleted:
                return reply(404)
            if self.failure == "cleanup_content" and self.content_reads == 2:
                return 200, b"another-document"
            return 200, self.content
        if route == own and method == "DELETE":
            self.deleted = True
            return reply(204)
        if route == own + "/analysis" and not token:
            return reply(401)
        if route == own + "/analysis":
            if self.failure == "timeout":
                raise TimeoutError("private-server-detail")
            if self.failure == "provider":
                return reply(503)
            if self.analysis is not None:
                return reply(200, {} if self.failure == "cache" else self.analysis)
            assert timeout > 3600
            marker = (
                self.content.decode().split("Codice pratica: ")[1].splitlines()[0].split(") Tj")[0]
            )
            self.analysis = {
                "id": str(uuid4()),
                "document_id": self.document,
                "facts": [{"source_text": marker}],
                "deadlines": [{"date": "2026-11-30", "source_text": "30 novembre 2026"}],
                "missing_information": ["Destinatario non indicato"],
            }
            if self.failure == "source":
                self.analysis["facts"] = []
            return reply(200, self.analysis)
        if route == own + "/analysis/latest" and self.analysis is not None:
            return reply(200, self.analysis) if token else reply(401)
        if route.endswith("/analysis/latest"):
            return reply(404)
        raise AssertionError("Unexpected mocked request")


@pytest.mark.parametrize(
    "failure",
    [None, "old_id", "bad_metadata", "cleanup_content", "provider", "timeout", "cache", "source"],
)
@pytest.mark.parametrize("pdf", [False, True])
def test_synthetic_analysis_cleanup_is_limited_and_failure_retains_document(
    monkeypatch, failure, pdf
):
    app = App(failure)
    monkeypatch.setattr(smoke, "request", app.request)
    result = {}
    if failure is None:
        smoke.run("private-email", "private-password", result, pdf=pdf)
        assert app.deleted
        assert result["synthetic_document_retained"] is False
        assert result["session_revoked"]
        assert result["persisted_analysis_verified"]
        assert result["unchanged_document_cached_result_verified"]
    else:
        with pytest.raises((smoke.Failure, TimeoutError)):
            smoke.run("private-email", "private-password", result, pdf=pdf)
        assert not app.deleted
    assert app.logged_out
    assert "private-token" not in repr(result)
    assert "private-password" not in repr(result)
    assert "private-server-detail" not in repr(result)
