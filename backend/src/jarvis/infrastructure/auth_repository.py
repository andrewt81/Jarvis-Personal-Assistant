from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, text

from jarvis.auth.models import Session, User
from jarvis.core.config import Settings


class OwnerAlreadyExistsError(Exception):
    """The one-time first-owner bootstrap has already been completed."""


class PostgreSQLAuthRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine_instance: Engine | None = None

    async def find_user_by_email(self, email: str) -> User | None:
        return await asyncio.to_thread(self._find_user_by_email, email)

    async def find_user_by_id(self, user_id: UUID) -> User | None:
        return await asyncio.to_thread(self._find_user_by_id, user_id)

    async def update_password_hash(self, user_id: UUID, password_hash: str) -> None:
        await asyncio.to_thread(self._update_password_hash, user_id, password_hash)

    async def create_session(self, session: Session) -> None:
        await asyncio.to_thread(self._create_session, session)

    async def find_session_by_access_hash(self, token_hash: bytes) -> Session | None:
        return await asyncio.to_thread(self._find_session, "access_token_hash", token_hash)

    async def find_session_by_refresh_hash(self, token_hash: bytes) -> Session | None:
        return await asyncio.to_thread(self._find_session, "refresh_token_hash", token_hash)

    async def rotate_session(
        self,
        session_id: UUID,
        *,
        expected_refresh_token_hash: bytes,
        access_token_hash: bytes,
        refresh_token_hash: bytes,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
    ) -> bool:
        return await asyncio.to_thread(
            self._rotate_session,
            session_id,
            expected_refresh_token_hash,
            access_token_hash,
            refresh_token_hash,
            access_expires_at,
            refresh_expires_at,
        )

    async def revoke_session(self, session_id: UUID, revoked_at: datetime) -> None:
        await asyncio.to_thread(self._revoke_session, session_id, revoked_at)

    def create_first_owner(
        self,
        *,
        email: str,
        password_hash: str,
        household_name: str,
        display_name: str,
    ) -> UUID:
        user_id = uuid4()
        household_id = uuid4()
        person_id = uuid4()
        with self._engine().begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('jarvis-first-owner'))"))
            if connection.execute(text("SELECT EXISTS (SELECT 1 FROM users)")).scalar_one():
                raise OwnerAlreadyExistsError
            connection.execute(
                text(
                    """
                    INSERT INTO users (id, email, password_hash)
                    VALUES (:id, :email, :password_hash)
                    """
                ),
                {"id": user_id, "email": email, "password_hash": password_hash},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO households (id, name, created_by_user_id)
                    VALUES (:id, :name, :user_id)
                    """
                ),
                {"id": household_id, "name": household_name, "user_id": user_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO household_memberships (household_id, user_id, role)
                    VALUES (:household_id, :user_id, 'owner')
                    """
                ),
                {"household_id": household_id, "user_id": user_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO people (id, household_id, display_name, kind, linked_user_id)
                    VALUES (:id, :household_id, :display_name, 'adult', :user_id)
                    """
                ),
                {
                    "id": person_id,
                    "household_id": household_id,
                    "display_name": display_name,
                    "user_id": user_id,
                },
            )
        return user_id

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

    def _find_user_by_email(self, email: str) -> User | None:
        with self._engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, email, password_hash, is_active
                    FROM users
                    WHERE email = :email
                    """
                ),
                {"email": email},
            ).first()
        return self._user_from_row(row)

    def _find_user_by_id(self, user_id: UUID) -> User | None:
        with self._engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, email, password_hash, is_active
                    FROM users
                    WHERE id = :id
                    """
                ),
                {"id": user_id},
            ).first()
        return self._user_from_row(row)

    def _update_password_hash(self, user_id: UUID, password_hash: str) -> None:
        with self._engine().begin() as connection:
            connection.execute(
                text("UPDATE users SET password_hash = :password_hash WHERE id = :id"),
                {"id": user_id, "password_hash": password_hash},
            )

    def _create_session(self, session: Session) -> None:
        with self._engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO auth_sessions (
                        id, user_id, access_token_hash, refresh_token_hash,
                        access_expires_at, expires_at
                    ) VALUES (
                        :id, :user_id, :access_token_hash, :refresh_token_hash,
                        :access_expires_at, :refresh_expires_at
                    )
                    """
                ),
                {
                    "id": session.id,
                    "user_id": session.user_id,
                    "access_token_hash": session.access_token_hash,
                    "refresh_token_hash": session.refresh_token_hash,
                    "access_expires_at": session.access_expires_at,
                    "refresh_expires_at": session.refresh_expires_at,
                },
            )

    def _find_session(self, column: str, token_hash: bytes) -> Session | None:
        statements = {
            "access_token_hash": text(
                """
                SELECT id, user_id, access_token_hash, refresh_token_hash,
                       access_expires_at, expires_at, revoked_at
                FROM auth_sessions
                WHERE access_token_hash = :token_hash
                """
            ),
            "refresh_token_hash": text(
                """
                SELECT id, user_id, access_token_hash, refresh_token_hash,
                       access_expires_at, expires_at, revoked_at
                FROM auth_sessions
                WHERE refresh_token_hash = :token_hash
                """
            ),
        }
        if column not in statements:
            raise ValueError("Unsupported session token column")
        with self._engine().connect() as connection:
            row = connection.execute(statements[column], {"token_hash": token_hash}).first()
        if row is None:
            return None
        values = row._mapping
        return Session(
            id=values["id"],
            user_id=values["user_id"],
            access_token_hash=bytes(values["access_token_hash"]),
            refresh_token_hash=bytes(values["refresh_token_hash"]),
            access_expires_at=values["access_expires_at"],
            refresh_expires_at=values["expires_at"],
            revoked_at=values["revoked_at"],
        )

    def _rotate_session(
        self,
        session_id: UUID,
        expected_refresh_token_hash: bytes,
        access_token_hash: bytes,
        refresh_token_hash: bytes,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
    ) -> bool:
        with self._engine().begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE auth_sessions
                    SET access_token_hash = :access_token_hash,
                        refresh_token_hash = :refresh_token_hash,
                        access_expires_at = :access_expires_at,
                        expires_at = :refresh_expires_at
                    WHERE id = :id
                      AND refresh_token_hash = :expected_refresh_token_hash
                      AND revoked_at IS NULL
                    """
                ),
                {
                    "id": session_id,
                    "expected_refresh_token_hash": expected_refresh_token_hash,
                    "access_token_hash": access_token_hash,
                    "refresh_token_hash": refresh_token_hash,
                    "access_expires_at": access_expires_at,
                    "refresh_expires_at": refresh_expires_at,
                },
            )
        return result.rowcount == 1

    def _revoke_session(self, session_id: UUID, revoked_at: datetime) -> None:
        with self._engine().begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE auth_sessions
                    SET revoked_at = :revoked_at
                    WHERE id = :id AND revoked_at IS NULL
                    """
                ),
                {"id": session_id, "revoked_at": revoked_at},
            )

    @staticmethod
    def _user_from_row(row: object | None) -> User | None:
        if row is None:
            return None
        values = row._mapping  # type: ignore[attr-defined]
        return User(
            id=values["id"],
            email=values["email"],
            password_hash=values["password_hash"],
            is_active=values["is_active"],
        )
