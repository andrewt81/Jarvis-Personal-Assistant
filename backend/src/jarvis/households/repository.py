from __future__ import annotations

from typing import Protocol
from uuid import UUID

from jarvis.households.models import Household, Membership, Person, PersonKind


class HouseholdRepository(Protocol):
    async def list_households(self, user_id: UUID) -> list[Household]: ...

    async def find_membership(self, user_id: UUID, household_id: UUID) -> Membership | None: ...

    async def list_people(self, household_id: UUID) -> list[Person]: ...

    async def create_person(
        self, household_id: UUID, display_name: str, kind: PersonKind
    ) -> Person: ...

    async def update_person(
        self,
        household_id: UUID,
        person_id: UUID,
        display_name: str,
        kind: PersonKind,
    ) -> Person | None: ...
