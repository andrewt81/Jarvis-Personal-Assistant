from __future__ import annotations

from uuid import UUID

from jarvis.households.models import Household, Person, PersonKind
from jarvis.households.repository import HouseholdRepository


class HouseholdNotFoundError(Exception):
    """The household is absent or invisible to the current user."""


class PersonNotFoundError(Exception):
    """The person is absent from the selected household."""


class HouseholdPermissionError(Exception):
    """The current membership does not allow the requested mutation."""


class HouseholdService:
    def __init__(self, repository: HouseholdRepository) -> None:
        self._repository = repository

    async def list_households(self, user_id: UUID) -> list[Household]:
        return await self._repository.list_households(user_id)

    async def list_people(self, user_id: UUID, household_id: UUID) -> list[Person]:
        await self._require_membership(user_id, household_id)
        return await self._repository.list_people(household_id)

    async def create_person(
        self,
        user_id: UUID,
        household_id: UUID,
        display_name: str,
        kind: PersonKind,
    ) -> Person:
        await self._require_editor(user_id, household_id)
        return await self._repository.create_person(household_id, display_name.strip(), kind)

    async def update_person(
        self,
        user_id: UUID,
        household_id: UUID,
        person_id: UUID,
        display_name: str,
        kind: PersonKind,
    ) -> Person:
        await self._require_editor(user_id, household_id)
        person = await self._repository.update_person(
            household_id, person_id, display_name.strip(), kind
        )
        if person is None:
            raise PersonNotFoundError
        return person

    async def _require_membership(self, user_id: UUID, household_id: UUID):
        membership = await self._repository.find_membership(user_id, household_id)
        if membership is None:
            raise HouseholdNotFoundError
        return membership

    async def _require_editor(self, user_id: UUID, household_id: UUID) -> None:
        membership = await self._require_membership(user_id, household_id)
        if membership.role not in {"owner", "adult"}:
            raise HouseholdPermissionError
