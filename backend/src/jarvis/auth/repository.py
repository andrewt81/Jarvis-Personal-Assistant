from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from jarvis.auth.models import Session, User


class AuthRepository(Protocol):
    async def find_user_by_email(self, email: str) -> User | None: ...

    async def find_user_by_id(self, user_id: UUID) -> User | None: ...

    async def update_password_hash(self, user_id: UUID, password_hash: str) -> None: ...

    async def create_session(self, session: Session) -> None: ...

    async def find_session_by_access_hash(self, token_hash: bytes) -> Session | None: ...

    async def find_session_by_refresh_hash(self, token_hash: bytes) -> Session | None: ...

    async def rotate_session(
        self,
        session_id: UUID,
        *,
        expected_refresh_token_hash: bytes,
        access_token_hash: bytes,
        refresh_token_hash: bytes,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
    ) -> bool: ...

    async def revoke_session(self, session_id: UUID, revoked_at: datetime) -> None: ...

    def create_first_owner(
        self,
        *,
        email: str,
        password_hash: str,
        household_name: str,
        display_name: str,
    ) -> UUID: ...
