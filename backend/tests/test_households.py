from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from jarvis.households.models import Household, Membership, Person, PersonKind
from jarvis.households.service import (
    HouseholdNotFoundError,
    HouseholdPermissionError,
    HouseholdService,
)


class InMemoryHouseholdRepository:
    def __init__(self) -> None:
        self.households: dict[UUID, Household] = {}
        self.memberships: dict[tuple[UUID, UUID], Membership] = {}
        self.people: dict[UUID, Person] = {}

    async def list_households(self, user_id: UUID) -> list[Household]:
        household_ids = {
            membership.household_id
            for membership in self.memberships.values()
            if membership.user_id == user_id
        }
        return [value for value in self.households.values() if value.id in household_ids]

    async def find_membership(self, user_id: UUID, household_id: UUID) -> Membership | None:
        return self.memberships.get((user_id, household_id))

    async def list_people(self, household_id: UUID) -> list[Person]:
        return [value for value in self.people.values() if value.household_id == household_id]

    async def create_person(
        self, household_id: UUID, display_name: str, kind: PersonKind
    ) -> Person:
        person = Person(
            id=uuid4(),
            household_id=household_id,
            display_name=display_name,
            kind=kind,
            linked_user_id=None,
            created_at=datetime.now(UTC),
        )
        self.people[person.id] = person
        return person

    async def update_person(
        self,
        household_id: UUID,
        person_id: UUID,
        display_name: str,
        kind: PersonKind,
    ) -> Person | None:
        current = self.people.get(person_id)
        if current is None or current.household_id != household_id:
            return None
        value = Person(
            id=current.id,
            household_id=current.household_id,
            display_name=display_name,
            kind=kind,
            linked_user_id=current.linked_user_id,
            created_at=current.created_at,
        )
        self.people[value.id] = value
        return value


def _repository(role: str = "owner") -> tuple[InMemoryHouseholdRepository, UUID, UUID]:
    repository = InMemoryHouseholdRepository()
    user_id = uuid4()
    household_id = uuid4()
    repository.households[household_id] = Household(
        id=household_id,
        name="Famiglia",
        role=role,  # type: ignore[arg-type]
        created_at=datetime.now(UTC),
    )
    repository.memberships[(user_id, household_id)] = Membership(
        household_id=household_id,
        user_id=user_id,
        role=role,  # type: ignore[arg-type]
    )
    return repository, user_id, household_id


def test_owner_can_manage_people() -> None:
    repository, user_id, household_id = _repository()
    service = HouseholdService(repository)
    created = asyncio.run(service.create_person(user_id, household_id, "  Giulia  ", "child"))
    assert created.display_name == "Giulia"
    updated = asyncio.run(
        service.update_person(user_id, household_id, created.id, "Giulia T.", "child")
    )
    assert updated.display_name == "Giulia T."


def test_viewer_can_read_but_cannot_modify_people() -> None:
    repository, user_id, household_id = _repository("viewer")
    service = HouseholdService(repository)
    assert asyncio.run(service.list_people(user_id, household_id)) == []
    with pytest.raises(HouseholdPermissionError):
        asyncio.run(service.create_person(user_id, household_id, "Giulia", "child"))


def test_non_member_cannot_detect_or_read_another_household() -> None:
    repository, _, household_id = _repository()
    service = HouseholdService(repository)
    stranger_id = uuid4()
    with pytest.raises(HouseholdNotFoundError):
        asyncio.run(service.list_people(stranger_id, household_id))
    with pytest.raises(HouseholdNotFoundError):
        asyncio.run(service.create_person(stranger_id, household_id, "Intruso", "other"))
