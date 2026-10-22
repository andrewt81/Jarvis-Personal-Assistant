from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskStatus = Literal["open", "done"]


@dataclass(frozen=True, slots=True)
class Task:
    id: UUID
    household_id: UUID
    person_id: UUID | None
    document_id: UUID | None
    created_by_user_id: UUID
    title: str
    notes: str
    priority: TaskPriority
    status: TaskStatus
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
