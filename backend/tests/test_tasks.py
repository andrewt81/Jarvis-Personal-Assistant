from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from jarvis.households.models import Membership
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError
from jarvis.tasks.models import Task
from jarvis.tasks.service import TaskService


class Households:
    def __init__(self, user_id: UUID, household_id: UUID, role: str = "owner") -> None:
        self.value = Membership(household_id, user_id, role)  # type: ignore[arg-type]

    async def find_membership(self, user_id: UUID, household_id: UUID):
        return (
            self.value
            if (user_id, household_id) == (self.value.user_id, self.value.household_id)
            else None
        )


class Tasks:
    def __init__(self) -> None:
        self.values: dict[UUID, Task] = {}

    async def list(self, household_id: UUID, include_done: bool) -> list[Task]:
        return [
            value
            for value in self.values.values()
            if value.household_id == household_id and (include_done or value.status == "open")
        ]

    async def create(self, task: Task) -> Task:
        now = datetime.now(UTC)
        value = replace(task, created_at=now, updated_at=now)
        self.values[value.id] = value
        return value

    async def update(self, task: Task) -> Task | None:
        current = self.values.get(task.id)
        if current is None or current.household_id != task.household_id:
            return None
        value = replace(
            task,
            created_at=current.created_at,
            updated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC) if task.status == "done" else None,
        )
        self.values[value.id] = value
        return value


def test_owner_creates_and_completes_prioritized_task() -> None:
    user_id, household_id = uuid4(), uuid4()
    repository = Tasks()
    service = TaskService(repository, Households(user_id, household_id))
    task = asyncio.run(
        service.create(
            user_id,
            household_id,
            title="  Pagare bolletta ",
            notes="",
            priority="urgent",
            due_at=None,
            person_id=None,
            document_id=None,
        )
    )
    assert task.title == "Pagare bolletta"
    done = asyncio.run(
        service.update(
            user_id,
            household_id,
            task.id,
            title=task.title,
            notes="",
            priority="urgent",
            status="done",
            due_at=None,
            person_id=None,
            document_id=None,
        )
    )
    assert done.status == "done"
    assert asyncio.run(service.list(user_id, household_id)) == []


def test_viewer_and_other_household_cannot_mutate() -> None:
    user_id, household_id = uuid4(), uuid4()
    service = TaskService(Tasks(), Households(user_id, household_id, "viewer"))
    with pytest.raises(HouseholdPermissionError):
        asyncio.run(
            service.create(
                user_id,
                household_id,
                title="No",
                notes="",
                priority="normal",
                due_at=None,
                person_id=None,
                document_id=None,
            )
        )
    with pytest.raises(HouseholdNotFoundError):
        asyncio.run(service.list(uuid4(), household_id))
