from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from jarvis.core.config import Settings
from jarvis.documents.models import Document


class PostgreSQLDocumentRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine_instance: Engine | None = None

    async def create(self, document: Document) -> Document:
        return await asyncio.to_thread(self._create, document)

    async def list(self, household_id: UUID) -> list[Document]:
        return await asyncio.to_thread(self._list, household_id)

    async def find(self, household_id: UUID, document_id: UUID) -> Document | None:
        return await asyncio.to_thread(self._find, household_id, document_id)

    async def delete(self, household_id: UUID, document_id: UUID) -> bool:
        return await asyncio.to_thread(self._delete, household_id, document_id)

    def _engine(self) -> Engine:
        if self._engine_instance is None:
            self._engine_instance = create_engine(
                self._settings.sqlalchemy_url(),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                connect_args={"connect_timeout": 5},
            )
        return self._engine_instance

    @staticmethod
    def _from_row(row) -> Document:
        values = dict(row._mapping)
        values["sha256"] = bytes(values["sha256"])
        return Document(**values)

    def _create(self, document: Document) -> Document:
        with self._engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        id, household_id, person_id, created_by_user_id, object_key,
                        original_filename, media_type, size_bytes, sha256
                    ) VALUES (
                        :id, :household_id, :person_id, :created_by_user_id, :object_key,
                        :original_filename, :media_type, :size_bytes, :sha256
                    )
                    RETURNING id, household_id, person_id, created_by_user_id, object_key,
                              original_filename, media_type, size_bytes, sha256, created_at
                    """
                ),
                {
                    "id": document.id,
                    "household_id": document.household_id,
                    "person_id": document.person_id,
                    "created_by_user_id": document.created_by_user_id,
                    "object_key": document.object_key,
                    "original_filename": document.original_filename,
                    "media_type": document.media_type,
                    "size_bytes": document.size_bytes,
                    "sha256": document.sha256,
                },
            ).one()
        return self._from_row(row)

    def _list(self, household_id: UUID) -> list[Document]:
        with self._engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, household_id, person_id, created_by_user_id, object_key,
                           original_filename, media_type, size_bytes, sha256, created_at
                    FROM documents
                    WHERE household_id = :household_id
                    ORDER BY created_at DESC, id
                    """
                ),
                {"household_id": household_id},
            ).all()
        return [self._from_row(row) for row in rows]

    def _find(self, household_id: UUID, document_id: UUID) -> Document | None:
        with self._engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, household_id, person_id, created_by_user_id, object_key,
                           original_filename, media_type, size_bytes, sha256, created_at
                    FROM documents
                    WHERE household_id = :household_id AND id = :id
                    """
                ),
                {"household_id": household_id, "id": document_id},
            ).first()
        return self._from_row(row) if row else None

    def _delete(self, household_id: UUID, document_id: UUID) -> bool:
        with self._engine().begin() as connection:
            result = connection.execute(
                text("DELETE FROM documents WHERE household_id = :household_id AND id = :id"),
                {"household_id": household_id, "id": document_id},
            )
        return result.rowcount == 1
