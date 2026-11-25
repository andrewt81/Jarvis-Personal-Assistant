from __future__ import annotations

import hashlib
import logging
from pathlib import PurePath
from typing import Protocol
from uuid import UUID, uuid4

from jarvis.documents.analysis import AnalysisUnavailableError, DocumentAnalyzer
from jarvis.documents.models import Document, DocumentAnalysis
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

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    """The document is absent or outside the current household."""


class InvalidDocumentError(Exception):
    """The supplied document violates the MVP upload policy."""


class DocumentRevisionConflict(Exception):
    """The original is superseded, concurrently changed, or belongs to a revision chain."""


class DocumentPreconditionFailed(Exception):
    """The supplied source hash does not match the selected original."""


class DocumentIntegrityError(Exception):
    """The stored original does not match the recorded length/hash."""


class DocumentRevisionUnavailable(Exception):
    """Persistence failed without a confirmed transaction outcome."""


class DocumentRepository(Protocol):
    async def create(self, document: Document) -> Document: ...

    async def list(self, household_id: UUID) -> list[Document]: ...

    async def find(self, household_id: UUID, document_id: UUID) -> Document | None: ...

    async def delete(self, household_id: UUID, document_id: UUID) -> bool: ...

    async def current(self, household_id: UUID, document_id: UUID) -> Document | None: ...

    async def revisions(self, household_id: UUID, document_id: UUID) -> list[Document]: ...

    async def create_revision(self, previous: Document, document: Document) -> Document | None: ...


class DocumentStorage(Protocol):
    async def put(self, key: str, content: bytes, media_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def get(self, key: str) -> bytes: ...


class DocumentAnalysisRepository(Protocol):
    async def create(self, analysis: DocumentAnalysis) -> DocumentAnalysis: ...

    async def latest(self, household_id: UUID, document_id: UUID) -> DocumentAnalysis | None: ...


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        households: HouseholdRepository,
        storage: DocumentStorage,
        analyses: DocumentAnalysisRepository | None = None,
        analyzer: DocumentAnalyzer | None = None,
    ) -> None:
        self._repository = repository
        self._households = households
        self._storage = storage
        self._analyses = analyses
        self._analyzer = analyzer

    async def list(self, user_id: UUID, household_id: UUID) -> list[Document]:
        await self._membership(user_id, household_id)
        return await self._repository.list(household_id)

    @staticmethod
    def _validate_file(filename: str, media_type: str, content: bytes) -> str:
        safe_name = PurePath(filename.replace("\\", "/")).name.strip()
        if not safe_name or len(safe_name) > 255:
            raise InvalidDocumentError("Invalid filename")
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise InvalidDocumentError("Unsupported media type")
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise InvalidDocumentError("Document size is outside the allowed range")
        return safe_name

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
        safe_name = self._validate_file(filename, media_type, content)
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
        return document, await self._read_original(document)

    async def current_revision(
        self, user_id: UUID, household_id: UUID, document_id: UUID
    ) -> Document:
        await self._membership(user_id, household_id)
        document = await self._repository.current(household_id, document_id)
        if document is None:
            raise DocumentNotFoundError
        return document

    async def revisions(
        self, user_id: UUID, household_id: UUID, document_id: UUID
    ) -> list[Document]:
        await self._membership(user_id, household_id)
        if await self._repository.find(household_id, document_id) is None:
            raise DocumentNotFoundError
        return await self._repository.revisions(household_id, document_id)

    async def create_revision(
        self,
        user_id: UUID,
        household_id: UUID,
        document_id: UUID,
        *,
        expected_sha256: bytes,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> Document:
        await self._editor(user_id, household_id)
        previous = await self._repository.find(household_id, document_id)
        if previous is None:
            raise DocumentNotFoundError
        if previous.sha256 != expected_sha256:
            raise DocumentPreconditionFailed
        await self._require_current(previous)
        safe_name = self._validate_file(filename, media_type, content)
        digest = hashlib.sha256(content).digest()
        if (digest, safe_name, media_type) == (
            previous.sha256,
            previous.original_filename,
            previous.media_type,
        ):
            return previous
        new_id = uuid4()
        document = Document(
            id=new_id,
            household_id=household_id,
            person_id=previous.person_id,
            created_by_user_id=user_id,
            object_key=f"households/{household_id}/documents/{new_id}/original",
            original_filename=safe_name,
            media_type=media_type,
            size_bytes=len(content),
            sha256=digest,
            created_at=None,
        )
        await self._storage.put(document.object_key, content, media_type)
        # Unknown DB failures may have an ambiguous commit outcome: retain the
        # unique candidate object rather than risk deleting a committed original.
        try:
            await self._editor(user_id, household_id)
        except (HouseholdNotFoundError, HouseholdPermissionError):
            await self._storage.delete(document.object_key)
            raise
        try:
            created = await self._repository.create_revision(previous, document)
        except Exception:
            logger.warning(
                "Revision candidate retained after persistence failure",
                extra={"document_id": str(document.id)},
            )
            raise DocumentRevisionUnavailable from None
        if created is None:
            # A confirmed lost race has made no DB changes. Only our new object
            # is removable; the selected original is never overwritten/deleted.
            await self._storage.delete(document.object_key)
            raise DocumentRevisionConflict
        return created

    async def delete(self, user_id: UUID, household_id: UUID, document_id: UUID) -> None:
        await self._editor(user_id, household_id)
        document = await self._repository.find(household_id, document_id)
        if document is None:
            raise DocumentNotFoundError
        if not await self._repository.delete(household_id, document_id):
            raise DocumentRevisionConflict
        # Database/FK checks run first so a concurrent revision cannot leave a
        # preserved document row pointing at an object we have already deleted.
        await self._storage.delete(document.object_key)

    async def analyze(
        self, user_id: UUID, household_id: UUID, document_id: UUID
    ) -> DocumentAnalysis:
        await self._editor(user_id, household_id)
        document = await self._repository.find(household_id, document_id)
        if document is None:
            raise DocumentNotFoundError
        await self._require_current(document)
        if self._analyses is None or self._analyzer is None:
            raise AnalysisUnavailableError("Document analysis is not enabled")
        existing = await self._analyses.latest(household_id, document_id)
        if existing is not None and existing.source_sha256 == document.sha256:
            await self._require_current(document)
            return existing
        content = await self._read_original(document)
        result = await self._analyzer.analyze(
            filename=document.original_filename,
            media_type=document.media_type,
            content=content,
        )
        await self._editor(user_id, household_id)
        await self._require_current(document)
        analysis = DocumentAnalysis(
            id=uuid4(),
            document_id=document.id,
            household_id=household_id,
            source_sha256=document.sha256,
            provider=result.provider,
            model=result.model,
            document_type=result.document_type,
            summary=result.summary,
            facts=result.facts,
            deadlines=result.deadlines,
            suggested_actions=result.suggested_actions,
            missing_information=result.missing_information,
            created_at=None,
        )
        stored = await self._analyses.create(analysis)
        await self._require_current(document)
        return stored

    async def latest_analysis(
        self, user_id: UUID, household_id: UUID, document_id: UUID
    ) -> DocumentAnalysis:
        await self._membership(user_id, household_id)
        document = await self._repository.find(household_id, document_id)
        if document is None:
            raise DocumentNotFoundError
        await self._require_current(document)
        if self._analyses is None:
            raise AnalysisUnavailableError("Document analysis is not enabled")
        analysis = await self._analyses.latest(household_id, document_id)
        if analysis is None or analysis.source_sha256 != document.sha256:
            raise DocumentNotFoundError
        await self._require_current(document)
        return analysis

    async def _read_original(self, document: Document) -> bytes:
        content = await self._storage.get(document.object_key)
        if (
            len(content) != document.size_bytes
            or hashlib.sha256(content).digest() != document.sha256
        ):
            raise DocumentIntegrityError
        return content

    async def _require_current(self, document: Document) -> None:
        current = await self._repository.current(document.household_id, document.id)
        if current is None:
            raise DocumentNotFoundError
        if current.id != document.id or current.sha256 != document.sha256:
            raise DocumentRevisionConflict

    async def _membership(self, user_id: UUID, household_id: UUID):
        membership = await self._households.find_membership(user_id, household_id)
        if membership is None:
            raise HouseholdNotFoundError
        return membership

    async def _editor(self, user_id: UUID, household_id: UUID) -> None:
        membership = await self._membership(user_id, household_id)
        if membership.role not in {"owner", "adult"}:
            raise HouseholdPermissionError
