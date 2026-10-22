from __future__ import annotations

import asyncio
import json
from pathlib import Path

from jarvis.core.config import Settings
from jarvis.documents.analysis import OpenAIDocumentAnalyzer


class FakeResponse:
    def __init__(self, body: object) -> None:
        self._body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_openai_analyzer_uses_private_structured_non_stored_response(
    monkeypatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "api-key"
    key_file.write_text("test-api-key", encoding="utf-8")
    settings = Settings.from_environment(
        {
            "JARVIS_AI_PROVIDER": "openai",
            "JARVIS_AI_MODEL": "gpt-6-luna",
            "JARVIS_AI_API_KEY_FILE": str(key_file),
        }
    )
    captured: dict[str, object] = {}
    output = {
        "document_type": "lettera",
        "summary": "Una lettera con una scadenza.",
        "facts": [{"label": "ente", "value": "Comune", "source_text": "Comune di Esempio"}],
        "deadlines": [
            {"date": "2026-11-30", "label": "Rispondere", "source_text": "entro il 30/11"}
        ],
        "suggested_actions": ["Preparare la risposta"],
        "missing_information": [],
    }

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(output)}],
                    }
                ]
            }
        )

    monkeypatch.setattr("jarvis.documents.analysis.urlopen", fake_urlopen)
    result = asyncio.run(
        OpenAIDocumentAnalyzer(settings).analyze(
            filename="lettera.pdf",
            media_type="application/pdf",
            content=b"%PDF-test",
        )
    )

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-6-luna"
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert payload["input"][0]["content"][0]["detail"] == "low"
    assert captured["authorization"] == "Bearer test-api-key"
    assert result.summary == output["summary"]
    assert result.suggested_actions == ("Preparare la risposta",)
