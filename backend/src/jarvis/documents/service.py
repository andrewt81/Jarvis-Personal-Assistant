from __future__ import annotations

import hashlib
from pathlib import PurePath
from typing import Protocol
from uuid import UUID, uuid4

from jarvis.documents.models import Document
from jarvis.households.repository import HouseholdRepository
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}


class DocumentNotFoundError(Exception):
    """The document is absent or outside the current household."""


class InvalidDocumentError(Exception):
    """The supplied document violates the MVP upload policy."""


class DocumentRepository(Protocol):
    async def create(self, document: Document) -> Document: ...

    async def list(self, household_id: UUID) -> list[Document]: ...

    async def find(self, household_id: UUID, document_id: UUID) -> Document | None: ...

    async def delete(self, household_id: UUID, document_id: UUID) -> bool: ...


class DocumentStorage(Protocol):
    async def put(self, key: str, content: bytes, media_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def get(self, key: str) -> bytes: ...


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        households: HouseholdRepository,
        storage: DocumentStorage,
    ) -> None:
        self._repository = repository
        self._households = households
        self._storage = storage

    async def list(self, user_id: UUID, household_id: UUID) -> list[Document]:
        await self._membership(user_id, household_id)
        return await self._repository.list(household_id)

    async def upload(
        self,
        user_id: UUID,
        household_id: UUID,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        person_id: UUID | None = None,
    ) -> Document:
        await self._editor(user_id, household_id)
        safe_name = PurePath(filename.replace("\\", "/")).name.strip()
        if not safe_name or len(safe_name) > 255:
            raise InvalidDocumentError("Invalid filename")
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise InvalidDocumentError("Unsupported media type")
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise InvalidDocumentError("Document size is outside the allowed range")
        if person_id is not None:
            people = await self._households.list_people(household_id)
            if not any(person.id == person_id for person in people):
                raise InvalidDocumentError("Person does not belong to household")

        document_id = uuid4()
        object_key = f"households/{household_id}/documents/{document_id}/original"
        digest = hashlib.sha256(content).digest()
        await self._storage.put(object_key, content, media_type)
        document = Document(
            id=document_id,
            household_id=household_id,
            person_id=person_id,
            created_by_user_id=user_id,
            object_key=object_key,
            original_filename=safe_name,
            media_type=media_type,
            size_bytes=len(content),
            sha256=digest,
            created_at=None,
        )
        try:
            return await self._repository.create(document)
        except Exception:
            await self._storage.delete(object_key)
            raise

    async def download(
        self, user_id: UUID, household_id: UUID, document_id: UUID
    ) -> tuple[Document, bytes]:
        await self._membership(user_id, household_id)
        document = await self._repository.find(household_id, document_id)
        if document is None:
            raise DocumentNotFoundError
        return document, await self._storage.get(document.object_key)

    async def delete(self, user_id: UUID, household_id: UUID, document_id: UUID) -> None:
        await self._editor(user_id, household_id)
        document = await self._repository.find(household_id, document_id)
        if document is None:
            raise DocumentNotFoundError
        await self._storage.delete(document.object_key)
        if not await self._repository.delete(household_id, document_id):
            raise DocumentNotFoundError

    async def _membership(self, user_id: UUID, household_id: UUID):
        membership = await self._households.find_membership(user_id, household_id)
        if membership is None:
            raise HouseholdNotFoundError
        return membership

    async def _editor(self, user_id: UUID, household_id: UUID) -> None:
        membership = await self._membership(user_id, household_id)
        if membership.role not in {"owner", "adult"}:
            raise HouseholdPermissionError
