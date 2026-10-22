from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from jarvis.core.config import Settings
from jarvis.documents.models import ExtractedDeadline, ExtractedFact


class AnalysisUnavailableError(Exception):
    """Document analysis is not configured or temporarily unavailable."""


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    provider: str
    model: str
    document_type: str
    summary: str
    facts: tuple[ExtractedFact, ...]
    deadlines: tuple[ExtractedDeadline, ...]
    suggested_actions: tuple[str, ...]
    missing_information: tuple[str, ...]


class DocumentAnalyzer(Protocol):
    async def analyze(
        self, *, filename: str, media_type: str, content: bytes
    ) -> AnalysisResult: ...


_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string"},
        "summary": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "source_text": {"type": "string"},
                },
                "required": ["label", "value", "source_text"],
                "additionalProperties": False,
            },
        },
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "label": {"type": "string"},
                    "source_text": {"type": "string"},
                },
                "required": ["date", "label", "source_text"],
                "additionalProperties": False,
            },
        },
        "suggested_actions": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "document_type",
        "summary",
        "facts",
        "deadlines",
        "suggested_actions",
        "missing_information",
    ],
    "additionalProperties": False,
}


class OpenAIDocumentAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def analyze(self, *, filename: str, media_type: str, content: bytes) -> AnalysisResult:
        return await asyncio.to_thread(
            self._analyze, filename=filename, media_type=media_type, content=content
        )

    def _analyze(self, *, filename: str, media_type: str, content: bytes) -> AnalysisResult:
        if self._settings.ai_provider != "openai":
            raise AnalysisUnavailableError("Document analysis is not enabled")
        try:
            api_key = self._settings.read_ai_api_key()
        except OSError as error:
            raise AnalysisUnavailableError(
                "Document analysis credentials are unavailable"
            ) from error

        encoded = base64.b64encode(content).decode("ascii")
        if media_type.startswith("image/"):
            file_input: dict[str, object] = {
                "type": "input_image",
                "image_url": f"data:{media_type};base64,{encoded}",
                "detail": "low",
            }
        else:
            file_input = {
                "type": "input_file",
                "filename": filename,
                "file_data": f"data:{media_type};base64,{encoded}",
            }
            if media_type == "application/pdf":
                file_input["detail"] = "low"
        payload = {
            "model": self._settings.ai_model,
            "store": False,
            "reasoning": {"effort": "low"},
            "instructions": (
                "Sei Jarvis, una segretaria digitale prudente. Analizza il documento in italiano. "
                "Distingui fatti testuali e suggerimenti. Non inventare dati mancanti. "
                "Per ogni fatto e scadenza cita un breve testo sorgente letterale. "
                "Le azioni sono solo proposte che l'utente dovrà confermare."
            ),
            "input": [
                {
                    "role": "user",
                    "content": [
                        file_input,
                        {
                            "type": "input_text",
                            "text": (
                                "Spiega cosa significa, cosa devo fare, entro quando e cosa manca. "
                                "Usa array vuoti quando il documento non contiene il dato."
                            ),
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "jarvis_document_analysis",
                    "strict": True,
                    "schema": _ANALYSIS_SCHEMA,
                }
            },
        }
        request = Request(  # noqa: S310 - fixed operator-configured API endpoint
            f"{self._settings.ai_api_base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:  # noqa: S310
                body = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise AnalysisUnavailableError("Document analysis request failed") from error
        text = self._output_text(body)
        try:
            value = json.loads(text)
            return AnalysisResult(
                provider="openai",
                model=self._settings.ai_model,
                document_type=str(value["document_type"]),
                summary=str(value["summary"]),
                facts=tuple(ExtractedFact(**item) for item in value["facts"]),
                deadlines=tuple(ExtractedDeadline(**item) for item in value["deadlines"]),
                suggested_actions=tuple(str(item) for item in value["suggested_actions"]),
                missing_information=tuple(str(item) for item in value["missing_information"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AnalysisUnavailableError("Document analysis response was invalid") from error

    @staticmethod
    def _output_text(body: object) -> str:
        if not isinstance(body, dict):
            raise AnalysisUnavailableError("Document analysis response was invalid")
        for item in body.get("output", []):
            if isinstance(item, dict) and item.get("type") == "message":
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") == "output_text":
                        return str(content.get("text", ""))
        raise AnalysisUnavailableError("Document analysis did not return structured output")
