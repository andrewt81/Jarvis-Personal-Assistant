from __future__ import annotations

import json
import logging
from contextlib import closing
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from jarvis.core.config import Settings
from jarvis.documents.analysis import AnalysisUnavailableError, OpenAIDocumentAnalyzer
from jarvis.documents.openwebui import (
    OpenWebUIDocumentAnalyzer,
    _Client,
    _NoRedirect,
    _private_base_url,
)
from jarvis.documents.providers import DisabledDocumentAnalyzer, create_document_analyzer
from jarvis.documents.service import DocumentNotFoundError, DocumentService
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError

OUTPUT = {
    "document_type": "lettera",
    "summary": "Risposta richiesta.",
    "facts": [{"label": "Ente", "value": "Comune", "source_text": "p. 1: Comune"}],
    "deadlines": [
        {"date": "2026-11-30", "label": "Rispondere", "source_text": "p. 1: entro il 30/11"}
    ],
    "suggested_actions": ["Preparare una bozza"],
    "missing_information": [],
}


class Response:
    def __init__(self, value: object):
        self.data = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, size: int):
        return self.data[:size]


class Server:
    def __init__(self):
        self.file_id = str(uuid4())
        self.chat_id = str(uuid4())
        self.chat = {}
        self.calls = []
        self.profile = {
            "id": "jarvis",
            "name": "Jarvis",
            "params": {"think": True, "num_ctx": 65536},
            "meta": {"toolIds": ["jarvis_original_pdf", "jarvis_decimal_calculator"]},
        }
        self.extraction = ["processing", "completed"]
        self.tasks = [["still-running"], []]
        self.done = [True, True]
        self.answer = json.dumps(OUTPUT)
        self.message_error = None
        self.rejected = False

    def open(self, request, timeout):
        route = urlsplit(request.full_url).path
        assert request.full_url.startswith("http://100.127.56.71:3000/")
        assert request.headers["Authorization"] == "Bearer application-test-key"
        assert 0 < timeout <= 90
        self.calls.append(request)
        if route == "/api/v1/models/model":
            return Response(self.profile)
        if route == "/api/v1/files/":
            assert b'filename="document.pdf"' in request.data
            assert b"%PDF-synthetic" in request.data
            assert b"private-filename" not in request.data
            return Response({"id": self.file_id})
        if route.endswith("/process/status"):
            return Response({"status": self.extraction.pop(0)})
        if route == f"/api/v1/files/{self.file_id}":
            return Response({"id": self.file_id, "user_id": "dedicated-service-user"})
        if route == "/api/v1/chats/new":
            self.chat = json.loads(request.data)["chat"]
            return Response({"id": self.chat_id})
        if route == "/api/chat/completions":
            payload = json.loads(request.data)
            self.completion = payload
            return Response({"error": "rejected"} if self.rejected else {"task_id": "task"})
        if route == f"/api/v1/chats/{self.chat_id}":
            assistant_id = self.chat["history"]["currentId"]
            return Response(
                {
                    "chat": {
                        "history": {
                            "currentId": assistant_id,
                            "messages": {
                                assistant_id: {
                                    "role": "assistant",
                                    "content": self.answer,
                                    "done": self.done.pop(0),
                                    "error": self.message_error,
                                    "output": [
                                        {"type": "reasoning", "content": "not-analyzed-or-returned"}
                                    ],
                                }
                            },
                        }
                    }
                }
            )
        if route == f"/api/tasks/chat/{self.chat_id}":
            return Response({"task_ids": self.tasks.pop(0)})
        raise AssertionError("Unexpected request " + route)


@pytest.fixture
def local_settings(tmp_path: Path):
    key = tmp_path / "service-key"
    key.write_text("application-test-key\n", encoding="utf-8")
    return Settings.from_environment(
        {
            "JARVIS_AI_PROVIDER": "openwebui",
            "JARVIS_OPENWEBUI_BASE_URL": "http://100.127.56.71:3000",
            "JARVIS_OPENWEBUI_API_KEY_FILE": str(key),
        }
    )


@pytest.fixture
def server(monkeypatch):
    instance = Server()
    monkeypatch.setattr("jarvis.documents.openwebui.build_opener", lambda *_: instance)
    monkeypatch.setattr("jarvis.documents.openwebui.time.sleep", lambda _: None)
    return instance


def analyze(settings):
    return OpenWebUIDocumentAnalyzer(settings)._analyze(
        filename="private-filename.pdf", media_type="application/pdf", content=b"%PDF-synthetic"
    )


def test_complete_attachment_native_tools_and_final_only(local_settings, server, caplog):
    caplog.set_level(logging.INFO)
    result = analyze(local_settings)
    assert result.provider == "openwebui" and result.model == "jarvis"
    assert result.summary == OUTPUT["summary"]
    assert result.facts[0].source_text == "p. 1: Comune"
    assert result.deadlines[0].date == "2026-11-30"
    payload = server.completion
    assert payload["params"] == {"function_calling": "native"}
    assert "think" not in payload["params"]  # Profile's boolean true remains authoritative.
    assert payload["tool_ids"] == server.profile["meta"]["toolIds"]
    assert payload["files"][0]["id"] == server.file_id
    assert payload["user_message"]["files"] == payload["files"]
    assert server.chat["files"] == payload["files"]
    assert len(payload["messages"]) == 1
    assert all(value is False for value in payload["features"].values())
    assert len([r for r in server.calls if "/api/tasks/chat/" in r.full_url]) == 2
    assert "not-analyzed-or-returned" not in repr(result)
    assert "application-test-key" not in caplog.text
    assert "%PDF-synthetic" not in caplog.text
    assert all(r.method in {"GET", "POST"} for r in server.calls)


@pytest.mark.parametrize(
    "change",
    [
        {"is_active": False},
        {"params": {"think": "true"}},
        {"params": {"think": False}},
        {"meta": {"toolIds": ["jarvis_original_pdf", "send_email"]}},
        {"meta": {"toolIds": ["jarvis_original_pdf"], "knowledge": [{"id": "foreign"}]}},
        {"meta": {"toolIds": ["jarvis_original_pdf"], "filterIds": ["unknown"]}},
        {"meta": {"toolIds": []}},
        {"meta": None},
        {"params": None},
    ],
)
def test_unsafe_profile_fails_before_upload(local_settings, server, change):
    server.profile.update(change)
    with pytest.raises(AnalysisUnavailableError):
        analyze(local_settings)
    assert len(server.calls) == 1


def test_wrong_profile_identity_prevents_upload(local_settings, server):
    server.profile["id"] = "different-model"
    with pytest.raises(AnalysisUnavailableError, match="model identity mismatch"):
        analyze(local_settings)
    assert len(server.calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://10.10.30.20:9000",
        "http://127.0.0.1:3000",
        "http://100.127.56.71:3000@evil.example",
        "http://user:secret@100.127.56.71:3000",
        "http://100.127.56.71:3000/path",
        "file:///etc/passwd",
        "",
        "http://100.127.56.71:wrong",
        "http://100.127.56.71:3000?token=secret",
    ],
)
def test_no_document_or_credential_to_non_tailnet_endpoint(local_settings, server, url):
    with pytest.raises(AnalysisUnavailableError):
        analyze(replace(local_settings, openwebui_base_url=url))
    assert server.calls == []


def test_redirect_refused_without_following_or_exposing_target():
    with pytest.raises(AnalysisUnavailableError, match="redirects are not allowed"):
        _NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")
    assert _private_base_url("http://100.127.56.71:3000/") == "http://100.127.56.71:3000"


def test_failed_extraction_never_starts_chat(local_settings, server):
    server.extraction = ["failed"]
    with pytest.raises(AnalysisUnavailableError, match="extraction failed"):
        analyze(local_settings)
    assert not server.chat


@pytest.mark.parametrize(
    "answer",
    [
        "```json\n" + json.dumps(OUTPUT) + "\n```",
        "not JSON",
        "[]",
        json.dumps({**OUTPUT, "summary": 123}),
        json.dumps({**OUTPUT, "facts": [{"label": "x", "value": "x", "source_text": ""}]}),
        json.dumps({**OUTPUT, "unexpected": "field"}),
        "<think>private reasoning</think>" + json.dumps(OUTPUT),
    ],
)
def test_invalid_output_never_becomes_an_analysis(local_settings, server, answer):
    server.answer = answer
    with pytest.raises(AnalysisUnavailableError, match="structured answer was invalid"):
        analyze(local_settings)


def test_remote_error_and_rejected_request_are_not_success(local_settings, server):
    server.message_error = {"content": "private upstream details"}
    with pytest.raises(AnalysisUnavailableError, match="analysis failed") as caught:
        analyze(local_settings)
    assert "private upstream details" not in str(caught.value)


def test_rejected_completion_is_not_polled(local_settings, server):
    server.rejected = True
    with pytest.raises(AnalysisUnavailableError, match="rejected"):
        analyze(local_settings)
    assert server.tasks == [["still-running"], []]


def test_done_false_not_accepted_even_without_tasks(local_settings, server):
    server.done = [False, True]
    server.tasks = [[], []]
    assert analyze(local_settings).summary == OUTPUT["summary"]
    assert server.done == []


def test_http_failure_redacts_response_and_credentials(local_settings, server):
    def fail(request, timeout):
        raise HTTPError(request.full_url, 401, "application-test-key", {}, BytesIO(b"private"))

    server.open = fail
    with pytest.raises(AnalysisUnavailableError) as caught:
        analyze(local_settings)
    assert str(caught.value) == "Open WebUI request failed"
    assert caught.value.__suppress_context__ is True


def test_deadline_and_key_failure_do_not_send_requests(local_settings, server):
    client = _Client(local_settings, 0)
    with pytest.raises(AnalysisUnavailableError, match="timed out"):
        client.request("GET", "/api/models")
    client.close()
    assert client._key == ""
    with pytest.raises(AnalysisUnavailableError, match="credentials are unavailable"):
        analyze(replace(local_settings, openwebui_api_key_file=Path("missing-key")))
    assert server.calls == []


def test_fresh_chat_for_every_analysis(local_settings, server):
    analyze(local_settings)
    first = server.completion["id"]
    server.extraction = ["completed"]
    server.tasks = [[]]
    server.done = [True]
    analyze(local_settings)
    assert server.completion["id"] != first
    assert len(server.completion["messages"]) == 1


def test_factory_never_falls_back_to_cloud(local_settings):
    assert isinstance(create_document_analyzer(local_settings), OpenWebUIDocumentAnalyzer)
    disabled = create_document_analyzer(replace(local_settings, ai_provider="unknown"))
    assert isinstance(disabled, DisabledDocumentAnalyzer)
    with pytest.raises(AnalysisUnavailableError):
        disabled.analyze(filename="x", media_type="text/plain", content=b"x").send(None)
    assert isinstance(
        create_document_analyzer(replace(local_settings, ai_provider="openai")),
        OpenAIDocumentAnalyzer,
    )


def complete_immediately(coroutine):
    """Drive in-memory coroutines without creating an OS event-loop socket.

    Any suspended await is an error. Network calls remain entirely simulated.
    """
    with closing(coroutine):
        try:
            coroutine.send(None)
        except StopIteration as finished:
            return finished.value
    raise AssertionError("The in-memory operation unexpectedly suspended")


def test_async_wrapper_delegates_without_changing_result(local_settings, server, monkeypatch):
    async def inline(function, **kwargs):
        return function(**kwargs)

    monkeypatch.setattr("jarvis.documents.openwebui.asyncio.to_thread", inline)
    result = complete_immediately(
        OpenWebUIDocumentAnalyzer(local_settings).analyze(
            filename="x.pdf", media_type="application/pdf", content=b"%PDF-synthetic"
        )
    )
    assert result.summary == OUTPUT["summary"]


@pytest.mark.parametrize(
    "membership, expected",
    [
        (None, HouseholdNotFoundError),
        ("viewer", HouseholdPermissionError),
        ("owner", DocumentNotFoundError),
    ],
)
def test_application_access_guard_precedes_ultron_upload(
    local_settings, server, membership, expected
):
    class Households:
        async def find_membership(self, user_id, household_id):
            return SimpleNamespace(role=membership) if membership else None

    class Documents:
        async def find(self, household_id, document_id):
            return None

    service = DocumentService(
        Documents(), Households(), None, analyzer=OpenWebUIDocumentAnalyzer(local_settings)
    )
    with pytest.raises(expected):
        complete_immediately(service.analyze(uuid4(), uuid4(), uuid4()))
    assert server.calls == []


def test_transport_has_bounded_response_and_does_not_use_proxies(local_settings, monkeypatch):
    import jarvis.documents.openwebui as module

    handlers = []

    class LargeResponse(Response):
        def read(self, size):
            return b"x" * size

    class Transport:
        def open(self, request, timeout):
            return LargeResponse({})

    def build(*values):
        handlers.extend(values)
        return Transport()

    monkeypatch.setattr(module, "build_opener", build)
    client = _Client(local_settings, module.time.monotonic() + 10)
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], _NoRedirect)
    with pytest.raises(AnalysisUnavailableError):
        client.request("GET", "/api/models")
    client.close()
