from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from jarvis.households.repository import HouseholdRepository
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError
from jarvis.tasks.models import Task, TaskPriority, TaskStatus


class TaskNotFoundError(Exception):
    """The task is absent or outside the selected household."""


class InvalidTaskReferenceError(Exception):
    """A linked person or document does not belong to the household."""


class TaskRepository(Protocol):
    async def list(self, household_id: UUID, include_done: bool) -> list[Task]: ...
    async def create(self, task: Task) -> Task | None: ...
    async def update(self, task: Task) -> Task | None: ...


class TaskService:
    def __init__(self, repository: TaskRepository, households: HouseholdRepository) -> None:
        self._repository = repository
        self._households = households

    async def list(
        self, user_id: UUID, household_id: UUID, include_done: bool = False
    ) -> list[Task]:
        await self._member(user_id, household_id)
        return await self._repository.list(household_id, include_done)

    async def create(
        self,
        user_id: UUID,
        household_id: UUID,
        *,
        title: str,
        notes: str,
        priority: TaskPriority,
        due_at: datetime | None,
        person_id: UUID | None,
        document_id: UUID | None,
    ) -> Task:
        await self._editor(user_id, household_id)
        task = Task(
            uuid4(),
            household_id,
            person_id,
            document_id,
            user_id,
            title.strip(),
            notes.strip(),
            priority,
            "open",
            due_at,
            None,
            None,
            None,
        )
        value = await self._repository.create(task)
        if value is None:
            raise InvalidTaskReferenceError
        return value

    async def update(
        self,
        user_id: UUID,
        household_id: UUID,
        task_id: UUID,
        *,
        title: str,
        notes: str,
        priority: TaskPriority,
        status: TaskStatus,
        due_at: datetime | None,
        person_id: UUID | None,
        document_id: UUID | None,
    ) -> Task:
        await self._editor(user_id, household_id)
        task = Task(
            task_id,
            household_id,
            person_id,
            document_id,
            user_id,
            title.strip(),
            notes.strip(),
            priority,
            status,
            due_at,
            None,
            None,
            None,
        )
        value = await self._repository.update(task)
        if value is None:
            raise TaskNotFoundError
        return value

    async def _member(self, user_id: UUID, household_id: UUID):
        membership = await self._households.find_membership(user_id, household_id)
        if membership is None:
            raise HouseholdNotFoundError
        return membership

    async def _editor(self, user_id: UUID, household_id: UUID) -> None:
        membership = await self._member(user_id, household_id)
        if membership.role not in {"owner", "adult"}:
            raise HouseholdPermissionError
