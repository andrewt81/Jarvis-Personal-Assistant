from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from jarvis.api.auth import current_user
from jarvis.auth.models import AuthenticatedUser
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError
from jarvis.tasks.models import Task
from jarvis.tasks.service import InvalidTaskReferenceError, TaskNotFoundError

router = APIRouter(prefix="/api/v1/households/{household_id}/tasks", tags=["tasks"])


class TaskWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=240)
    notes: str = Field(default="", max_length=10000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    status: Literal["open", "done"] = "open"
    due_at: datetime | None = None
    person_id: UUID | None = None
    document_id: UUID | None = None


class TaskResponse(TaskWrite):
    id: UUID
    household_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


def _response(value: Task) -> TaskResponse:
    if value.created_at is None or value.updated_at is None:
        raise RuntimeError("Persisted task is missing timestamps")
    return TaskResponse(**{name: getattr(value, name) for name in TaskResponse.model_fields})


def _error(error: Exception) -> HTTPException:
    if isinstance(error, (HouseholdNotFoundError, TaskNotFoundError)):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(error, HouseholdPermissionError):
        return HTTPException(status_code=403, detail="Insufficient permissions")
    return HTTPException(status_code=422, detail="Linked resource does not belong to household")


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    household_id: UUID,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    include_done: bool = False,
) -> list[TaskResponse]:
    try:
        values = await request.app.state.task_service.list(user.id, household_id, include_done)
    except HouseholdNotFoundError as error:
        raise _error(error) from error
    return [_response(value) for value in values]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    household_id: UUID,
    payload: TaskWrite,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> TaskResponse:
    try:
        value = await request.app.state.task_service.create(
            user.id, household_id, **payload.model_dump(exclude={"status"})
        )
    except (HouseholdNotFoundError, HouseholdPermissionError, InvalidTaskReferenceError) as error:
        raise _error(error) from error
    return _response(value)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    household_id: UUID,
    task_id: UUID,
    payload: TaskWrite,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> TaskResponse:
    try:
        value = await request.app.state.task_service.update(
            user.id, household_id, task_id, **payload.model_dump()
        )
    except (
        HouseholdNotFoundError,
        HouseholdPermissionError,
        TaskNotFoundError,
        InvalidTaskReferenceError,
    ) as error:
        raise _error(error) from error
    return _response(value)
