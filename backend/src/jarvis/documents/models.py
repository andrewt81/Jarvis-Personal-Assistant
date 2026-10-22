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
