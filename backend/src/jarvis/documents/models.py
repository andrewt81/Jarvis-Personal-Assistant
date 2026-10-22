from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Document:
    id: UUID
    household_id: UUID
    person_id: UUID | None
    created_by_user_id: UUID
    object_key: str
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: bytes
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    label: str
    value: str
    source_text: str


@dataclass(frozen=True, slots=True)
class ExtractedDeadline:
    date: str
    label: str
    source_text: str


@dataclass(frozen=True, slots=True)
class DocumentAnalysis:
    id: UUID
    document_id: UUID
    household_id: UUID
    source_sha256: bytes
    provider: str
    model: str
    document_type: str
    summary: str
    facts: tuple[ExtractedFact, ...]
    deadlines: tuple[ExtractedDeadline, ...]
    suggested_actions: tuple[str, ...]
    missing_information: tuple[str, ...]
    created_at: datetime | None
