from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, text

from jarvis.core.config import Settings
from jarvis.households.models import Household, Membership, Person, PersonKind


class PostgreSQLHouseholdRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine_instance: Engine | None = None

    async def list_households(self, user_id: UUID) -> list[Household]:
        return await asyncio.to_thread(self._list_households, user_id)

    async def find_membership(self, user_id: UUID, household_id: UUID) -> Membership | None:
        return await asyncio.to_thread(self._find_membership, user_id, household_id)

    async def list_people(self, household_id: UUID) -> list[Person]:
        return await asyncio.to_thread(self._list_people, household_id)

    async def create_person(
        self, household_id: UUID, display_name: str, kind: PersonKind
    ) -> Person:
        return await asyncio.to_thread(self._create_person, household_id, display_name, kind)

    async def update_person(
        self,
        household_id: UUID,
        person_id: UUID,
        display_name: str,
        kind: PersonKind,
    ) -> Person | None:
        return await asyncio.to_thread(
            self._update_person, household_id, person_id, display_name, kind
        )

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

    def _list_households(self, user_id: UUID) -> list[Household]:
        with self._engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT h.id, h.name, hm.role, h.created_at
                    FROM households h
                    JOIN household_memberships hm ON hm.household_id = h.id
                    WHERE hm.user_id = :user_id
                    ORDER BY h.created_at, h.id
                    """
                ),
                {"user_id": user_id},
            ).all()
        return [Household(**dict(row._mapping)) for row in rows]

    def _find_membership(self, user_id: UUID, household_id: UUID) -> Membership | None:
        with self._engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT household_id, user_id, role
                    FROM household_memberships
                    WHERE household_id = :household_id AND user_id = :user_id
                    """
                ),
                {"household_id": household_id, "user_id": user_id},
            ).first()
        return Membership(**dict(row._mapping)) if row else None

    def _list_people(self, household_id: UUID) -> list[Person]:
        with self._engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, household_id, display_name, kind, linked_user_id, created_at
                    FROM people
                    WHERE household_id = :household_id
                    ORDER BY created_at, id
                    """
                ),
                {"household_id": household_id},
            ).all()
        return [Person(**dict(row._mapping)) for row in rows]

    def _create_person(self, household_id: UUID, display_name: str, kind: PersonKind) -> Person:
        person_id = uuid4()
        with self._engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO people (id, household_id, display_name, kind)
                    VALUES (:id, :household_id, :display_name, :kind)
                    RETURNING id, household_id, display_name, kind, linked_user_id, created_at
                    """
                ),
                {
                    "id": person_id,
                    "household_id": household_id,
                    "display_name": display_name,
                    "kind": kind,
                },
            ).one()
        return Person(**dict(row._mapping))

    def _update_person(
        self,
        household_id: UUID,
        person_id: UUID,
        display_name: str,
        kind: PersonKind,
    ) -> Person | None:
        with self._engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    UPDATE people
                    SET display_name = :display_name, kind = :kind
                    WHERE id = :id AND household_id = :household_id
                    RETURNING id, household_id, display_name, kind, linked_user_id, created_at
                    """
                ),
                {
                    "id": person_id,
                    "household_id": household_id,
                    "display_name": display_name,
                    "kind": kind,
                },
            ).first()
        return Person(**dict(row._mapping)) if row else None
