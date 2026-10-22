from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from jarvis.api.auth import current_user
from jarvis.auth.models import AuthenticatedUser
from jarvis.households.models import Household, Person
from jarvis.households.service import (
    HouseholdNotFoundError,
    HouseholdPermissionError,
    HouseholdService,
    PersonNotFoundError,
)

router = APIRouter(prefix="/api/v1/households", tags=["households"])


class HouseholdResponse(BaseModel):
    id: UUID
    name: str
    role: Literal["owner", "adult", "viewer"]
    created_at: datetime


class PersonResponse(BaseModel):
    id: UUID
    household_id: UUID
    display_name: str
    kind: Literal["adult", "child", "other"]
    linked_user_id: UUID | None
    created_at: datetime


class PersonWriteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=160)
    kind: Literal["adult", "child", "other"]


def _service(request: Request) -> HouseholdService:
    return request.app.state.household_service


def _household_response(value: Household) -> HouseholdResponse:
    return HouseholdResponse(**asdict(value))


def _person_response(value: Person) -> PersonResponse:
    return PersonResponse(**asdict(value))


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, (HouseholdNotFoundError, PersonNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.get("", response_model=list[HouseholdResponse])
async def list_households(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[HouseholdResponse]:
    values = await _service(request).list_households(user.id)
    return [_household_response(value) for value in values]


@router.get("/{household_id}/people", response_model=list[PersonResponse])
async def list_people(
    household_id: UUID,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[PersonResponse]:
    try:
        values = await _service(request).list_people(user.id, household_id)
    except HouseholdNotFoundError as error:
        raise _translate(error) from error
    return [_person_response(value) for value in values]


@router.post(
    "/{household_id}/people",
    response_model=PersonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_person(
    household_id: UUID,
    payload: PersonWriteRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> PersonResponse:
    try:
        value = await _service(request).create_person(
            user.id, household_id, payload.display_name, payload.kind
        )
    except (HouseholdNotFoundError, HouseholdPermissionError) as error:
        raise _translate(error) from error
    return _person_response(value)


@router.put("/{household_id}/people/{person_id}", response_model=PersonResponse)
async def update_person(
    household_id: UUID,
    person_id: UUID,
    payload: PersonWriteRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> PersonResponse:
    try:
        value = await _service(request).update_person(
            user.id, household_id, person_id, payload.display_name, payload.kind
        )
    except (HouseholdNotFoundError, HouseholdPermissionError, PersonNotFoundError) as error:
        raise _translate(error) from error
    return _person_response(value)
