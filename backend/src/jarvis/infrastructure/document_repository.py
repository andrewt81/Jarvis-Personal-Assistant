from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

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

    async def current(self, household_id: UUID, document_id: UUID) -> Document | None:
        return await asyncio.to_thread(self._current, household_id, document_id)

    async def revisions(self, household_id: UUID, document_id: UUID) -> list[Document]:
        return await asyncio.to_thread(self._revisions, household_id, document_id)

    async def create_revision(self, previous: Document, document: Document) -> Document | None:
        return await asyncio.to_thread(self._create_revision, previous, document)

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
            return self._insert(connection, document)

    def _insert(self, connection, document: Document) -> Document:
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

    def _create_revision(self, previous: Document, document: Document) -> Document | None:
        with self._engine().begin() as connection:
            row = connection.execute(
                text("""
                    SELECT sha256 FROM documents
                    WHERE id=:id AND household_id=:household_id FOR UPDATE
                """),
                {"id": previous.id, "household_id": previous.household_id},
            ).first()
            if row is None or bytes(row.sha256) != previous.sha256:
                return None
            if connection.execute(
                text("SELECT 1 FROM document_revisions WHERE previous_document_id=:id"),
                {"id": previous.id},
            ).first():
                return None
            if document.household_id != previous.household_id or document.id == previous.id:
                raise ValueError("Invalid document revision identity")
            created = self._insert(connection, document)
            connection.execute(
                text("""
                    INSERT INTO document_revisions
                        (previous_document_id,document_id,household_id)
                    VALUES (:previous_id,:document_id,:household_id)
                """),
                {
                    "previous_id": previous.id,
                    "document_id": document.id,
                    "household_id": previous.household_id,
                },
            )
        return created

    def _list(self, household_id: UUID) -> list[Document]:
        with self._engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, household_id, person_id, created_by_user_id, object_key,
                           original_filename, media_type, size_bytes, sha256, created_at
                    FROM documents
                    WHERE household_id = :household_id
                      AND NOT EXISTS (
                        SELECT 1 FROM document_revisions r
                        WHERE r.previous_document_id=documents.id
                      )
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
        try:
            with self._engine().begin() as connection:
                result = connection.execute(
                    text("""
                        DELETE FROM documents WHERE household_id=:household_id AND id=:id
                        AND NOT EXISTS (
                            SELECT 1 FROM document_revisions r
                            WHERE r.previous_document_id=:id OR r.document_id=:id
                        )
                    """),
                    {"household_id": household_id, "id": document_id},
                )
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23503":
                return False
            raise
        return result.rowcount == 1

    def _current(self, household_id: UUID, document_id: UUID) -> Document | None:
        with self._engine().connect() as connection:
            row = connection.execute(
                text("""
                    WITH RECURSIVE descendants(id) AS (
                        SELECT id FROM documents WHERE id=:id AND household_id=:household_id
                        UNION
                        SELECT r.document_id FROM document_revisions r
                        JOIN descendants p ON p.id=r.previous_document_id
                        WHERE r.household_id=:household_id
                    )
                    SELECT d.id,d.household_id,d.person_id,d.created_by_user_id,d.object_key,
                           d.original_filename,d.media_type,d.size_bytes,d.sha256,d.created_at
                    FROM descendants c JOIN documents d ON d.id=c.id
                    WHERE d.household_id=:household_id AND NOT EXISTS (
                        SELECT 1 FROM document_revisions r WHERE r.previous_document_id=d.id
                    )
                """),
                {"id": document_id, "household_id": household_id},
            ).first()
        return self._from_row(row) if row else None

    def _revisions(self, household_id: UUID, document_id: UUID) -> list[Document]:
        with self._engine().connect() as connection:
            rows = connection.execute(
                text("""
                    WITH RECURSIVE family(id) AS (
                        SELECT id FROM documents WHERE id=:id AND household_id=:household_id
                        UNION
                        SELECT CASE WHEN r.previous_document_id=f.id
                                    THEN r.document_id ELSE r.previous_document_id END
                        FROM family f JOIN document_revisions r
                          ON r.previous_document_id=f.id OR r.document_id=f.id
                        WHERE r.household_id=:household_id
                    )
                    SELECT d.id,d.household_id,d.person_id,d.created_by_user_id,d.object_key,
                           d.original_filename,d.media_type,d.size_bytes,d.sha256,d.created_at
                    FROM family f JOIN documents d ON d.id=f.id
                    WHERE d.household_id=:household_id
                    ORDER BY d.created_at,d.id
                """),
                {"id": document_id, "household_id": household_id},
            ).all()
        return [self._from_row(row) for row in rows]
