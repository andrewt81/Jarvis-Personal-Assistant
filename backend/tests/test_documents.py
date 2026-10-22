from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from jarvis.documents.models import Document
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
