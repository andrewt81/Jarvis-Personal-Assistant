from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from jarvis.core.config import Settings
from jarvis.tasks.models import Task


class PostgreSQLTaskRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine_instance: Engine | None = None

    async def list(self, household_id: UUID, include_done: bool) -> list[Task]:
        return await asyncio.to_thread(self._list, household_id, include_done)

    async def create(self, task: Task) -> Task | None:
        return await asyncio.to_thread(self._create, task)

    async def update(self, task: Task) -> Task | None:
        return await asyncio.to_thread(self._update, task)

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
    def _row(row) -> Task:
        return Task(**dict(row._mapping))

    def _list(self, household_id: UUID, include_done: bool) -> list[Task]:
        base = """
            SELECT id, household_id, person_id, document_id, created_by_user_id, title,
                   notes, priority, status, due_at, completed_at, created_at, updated_at
            FROM tasks WHERE household_id = :household_id
            ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                         WHEN 'normal' THEN 2 ELSE 3 END,
                     due_at NULLS LAST, created_at
        """
        open_only = base.replace("ORDER BY", "AND status = 'open' ORDER BY", 1)
        statement = text(base if include_done else open_only)
        with self._engine().connect() as connection:
            rows = connection.execute(statement, {"household_id": household_id}).all()
        return [self._row(row) for row in rows]

    @staticmethod
    def _values(task: Task) -> dict[str, object]:
        return {
            "id": task.id,
            "household_id": task.household_id,
            "person_id": task.person_id,
            "document_id": task.document_id,
            "user_id": task.created_by_user_id,
            "title": task.title,
            "notes": task.notes,
            "priority": task.priority,
            "status": task.status,
            "due_at": task.due_at,
        }

    def _create(self, task: Task) -> Task | None:
        with self._engine().begin() as connection:
            row = connection.execute(
                text("""
                INSERT INTO tasks (id, household_id, person_id, document_id, created_by_user_id,
                                   title, notes, priority, status, due_at)
                SELECT :id, :household_id, CAST(:person_id AS uuid),
                       CAST(:document_id AS uuid), :user_id,
                       :title, :notes, :priority, 'open', :due_at
                WHERE (CAST(:person_id AS uuid) IS NULL OR EXISTS (
                    SELECT 1 FROM people
                    WHERE id = CAST(:person_id AS uuid) AND household_id = :household_id))
                  AND (CAST(:document_id AS uuid) IS NULL OR EXISTS (
                    SELECT 1 FROM documents
                    WHERE id = CAST(:document_id AS uuid) AND household_id = :household_id))
                RETURNING id, household_id, person_id, document_id, created_by_user_id, title,
                          notes, priority, status, due_at, completed_at, created_at, updated_at
            """),
                self._values(task),
            ).first()
        return self._row(row) if row else None

    def _update(self, task: Task) -> Task | None:
        with self._engine().begin() as connection:
            row = connection.execute(
                text("""
                UPDATE tasks SET person_id = CAST(:person_id AS uuid),
                    document_id = CAST(:document_id AS uuid),
                    title = :title, notes = :notes, priority = CAST(:priority AS varchar),
                    status = CAST(:status AS varchar),
                    due_at = :due_at,
                    completed_at = CASE WHEN CAST(:status AS varchar) = 'done'
                        THEN COALESCE(completed_at, now()) ELSE NULL END,
                    updated_at = now()
                WHERE id = :id AND household_id = :household_id
                  AND (CAST(:person_id AS uuid) IS NULL OR EXISTS (
                    SELECT 1 FROM people
                    WHERE id = CAST(:person_id AS uuid) AND household_id = :household_id))
                  AND (CAST(:document_id AS uuid) IS NULL OR EXISTS (
                    SELECT 1 FROM documents
                    WHERE id = CAST(:document_id AS uuid) AND household_id = :household_id))
                RETURNING id, household_id, person_id, document_id, created_by_user_id, title,
                          notes, priority, status, due_at, completed_at, created_at, updated_at
            """),
                self._values(task),
            ).first()
        return self._row(row) if row else None
