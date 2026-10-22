from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from jarvis.documents.analysis import AnalysisResult
from jarvis.documents.models import (
    Document,
    DocumentAnalysis,
    ExtractedDeadline,
    ExtractedFact,
)
from jarvis.documents.service import DocumentService, InvalidDocumentError
from jarvis.households.models import Membership
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError


class Households:
    def __init__(self, user_id: UUID, household_id: UUID, role: str = "owner") -> None:
        self.membership = Membership(household_id, user_id, role)  # type: ignore[arg-type]

    async def find_membership(self, user_id: UUID, household_id: UUID):
        value = self.membership
        return value if (value.user_id, value.household_id) == (user_id, household_id) else None

    async def list_people(self, household_id: UUID):
        return []


class Documents:
    def __init__(self) -> None:
        self.values: dict[UUID, Document] = {}

    async def create(self, document: Document) -> Document:
        value = replace(document, created_at=datetime.now(UTC))
        self.values[value.id] = value
        return value

    async def list(self, household_id: UUID) -> list[Document]:
        return [value for value in self.values.values() if value.household_id == household_id]

    async def find(self, household_id: UUID, document_id: UUID) -> Document | None:
        value = self.values.get(document_id)
        return value if value and value.household_id == household_id else None

    async def delete(self, household_id: UUID, document_id: UUID) -> bool:
        value = await self.find(household_id, document_id)
        if value is None:
            return False
        del self.values[document_id]
        return True


class Storage:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes, media_type: str) -> None:
        self.values[key] = content

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def get(self, key: str) -> bytes:
        return self.values[key]


class Analyses:
    def __init__(self) -> None:
        self.values: list[DocumentAnalysis] = []

    async def create(self, analysis: DocumentAnalysis) -> DocumentAnalysis:
        value = replace(analysis, created_at=datetime.now(UTC))
        self.values.append(value)
        return value

    async def latest(self, household_id: UUID, document_id: UUID) -> DocumentAnalysis | None:
        matches = [
            value
            for value in self.values
            if value.household_id == household_id and value.document_id == document_id
        ]
        return matches[-1] if matches else None


class Analyzer:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, *, filename: str, media_type: str, content: bytes) -> AnalysisResult:
        self.calls += 1
        assert filename == "lettera.txt"
        assert media_type == "text/plain"
        assert content == b"Scadenza: 2026-11-30"
        return AnalysisResult(
            provider="test",
            model="test-model",
            document_type="comunicazione",
            summary="Una comunicazione con una scadenza.",
            facts=(ExtractedFact("scadenza", "2026-11-30", "Scadenza: 2026-11-30"),),
            deadlines=(ExtractedDeadline("2026-11-30", "Rispondere", "Scadenza: 2026-11-30"),),
            suggested_actions=("Preparare la risposta",),
            missing_information=("Destinatario",),
        )


def test_upload_hashes_and_namespaces_original() -> None:
    user_id, household_id = uuid4(), uuid4()
    repository, storage = Documents(), Storage()
    service = DocumentService(repository, Households(user_id, household_id), storage)
    document = asyncio.run(
        service.upload(
            user_id,
            household_id,
            filename="../referto.pdf",
            media_type="application/pdf",
            content=b"private document",
        )
    )
    assert document.original_filename == "referto.pdf"
    assert document.object_key.startswith(f"households/{household_id}/documents/")
    assert (
        document.sha256.hex() == "342b55d4f3a1e171fe06aec7e6389cbd03db9f07759873cbaadb017ca8ac1076"
    )
    assert storage.values[document.object_key] == b"private document"


def test_viewer_cannot_upload_but_can_list() -> None:
    user_id, household_id = uuid4(), uuid4()
    service = DocumentService(Documents(), Households(user_id, household_id, "viewer"), Storage())
    assert asyncio.run(service.list(user_id, household_id)) == []
    with pytest.raises(HouseholdPermissionError):
        asyncio.run(
            service.upload(
                user_id,
                household_id,
                filename="file.pdf",
                media_type="application/pdf",
                content=b"content",
            )
        )


def test_other_household_is_hidden_and_invalid_types_are_rejected() -> None:
    user_id, household_id = uuid4(), uuid4()
    service = DocumentService(Documents(), Households(user_id, household_id), Storage())
    with pytest.raises(HouseholdNotFoundError):
        asyncio.run(service.list(uuid4(), household_id))
    with pytest.raises(InvalidDocumentError):
        asyncio.run(
            service.upload(
                user_id,
                household_id,
                filename="payload.exe",
                media_type="application/octet-stream",
                content=b"not allowed",
            )
        )


def test_document_analysis_preserves_sources_and_requires_explicit_task_creation() -> None:
    user_id, household_id = uuid4(), uuid4()
    repository, storage, analyses = Documents(), Storage(), Analyses()
    analyzer = Analyzer()
    service = DocumentService(
        repository,
        Households(user_id, household_id),
        storage,
        analyses,
        analyzer,
    )
    document = asyncio.run(
        service.upload(
            user_id,
            household_id,
            filename="lettera.txt",
            media_type="text/plain",
            content=b"Scadenza: 2026-11-30",
        )
    )

    analysis = asyncio.run(service.analyze(user_id, household_id, document.id))
    latest = asyncio.run(service.latest_analysis(user_id, household_id, document.id))
    cached = asyncio.run(service.analyze(user_id, household_id, document.id))

    assert latest == analysis
    assert cached == analysis
    assert analyzer.calls == 1
    assert analysis.source_sha256 == document.sha256
    assert analysis.facts[0].source_text == "Scadenza: 2026-11-30"
    assert analysis.suggested_actions == ("Preparare la risposta",)
