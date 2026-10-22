from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jarvis.auth.models import AuthenticatedUser, Session, TokenPair, User
from jarvis.auth.passwords import PasswordManager
from jarvis.auth.repository import AuthRepository


class AuthenticationError(Exception):
    """Authentication failed without exposing which credential was incorrect."""


class InvalidSessionError(Exception):
    """A session token is missing, expired, rotated or revoked."""


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        password_manager: PasswordManager | None = None,
        now: Callable[[], datetime] | None = None,
        access_lifetime: timedelta = timedelta(minutes=15),
        refresh_lifetime: timedelta = timedelta(days=30),
    ) -> None:
        self._repository = repository
        self._passwords = password_manager or PasswordManager()
        self._now = now or (lambda: datetime.now(UTC))
        self._access_lifetime = access_lifetime
        self._refresh_lifetime = refresh_lifetime

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self._repository.find_user_by_email(self.normalize_email(email))
        if user is None:
            await asyncio.to_thread(self._passwords.verify_dummy, password)
            raise AuthenticationError
        password_valid = await asyncio.to_thread(
            self._passwords.verify, user.password_hash, password
        )
        if not user.is_active or not password_valid:
            raise AuthenticationError
        if self._passwords.needs_rehash(user.password_hash):
            updated_hash = await asyncio.to_thread(self._passwords.hash, password)
            await self._repository.update_password_hash(user.id, updated_hash)
        return await self._new_session(user)

    async def authenticate(self, access_token: str) -> AuthenticatedUser:
        now = self._now()
        session = await self._repository.find_session_by_access_hash(self.hash_token(access_token))
        if session is None or session.revoked_at is not None or session.access_expires_at <= now:
            raise InvalidSessionError
        user = await self._repository.find_user_by_id(session.user_id)
        if user is None or not user.is_active:
            raise InvalidSessionError
        return AuthenticatedUser(id=user.id, email=user.email)

    async def refresh(self, refresh_token: str) -> TokenPair:
        now = self._now()
        session = await self._repository.find_session_by_refresh_hash(
            self.hash_token(refresh_token)
        )
        if session is None or session.revoked_at is not None or session.refresh_expires_at <= now:
            raise InvalidSessionError
        user = await self._repository.find_user_by_id(session.user_id)
        if user is None or not user.is_active:
            raise InvalidSessionError

        access_token = self.generate_token()
        next_refresh_token = self.generate_token()
        access_expires_at = now + self._access_lifetime
        refresh_expires_at = now + self._refresh_lifetime
        rotated = await self._repository.rotate_session(
            session.id,
            expected_refresh_token_hash=session.refresh_token_hash,
            access_token_hash=self.hash_token(access_token),
            refresh_token_hash=self.hash_token(next_refresh_token),
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )
        if not rotated:
            raise InvalidSessionError
        return TokenPair(
            access_token=access_token,
            refresh_token=next_refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            user=AuthenticatedUser(id=user.id, email=user.email),
        )

    async def logout(self, access_token: str) -> None:
        session = await self._repository.find_session_by_access_hash(self.hash_token(access_token))
        if session is not None and session.revoked_at is None:
            await self._repository.revoke_session(session.id, self._now())

    async def _new_session(self, user: User) -> TokenPair:
        now = self._now()
        access_token = self.generate_token()
        refresh_token = self.generate_token()
        session = Session(
            id=uuid4(),
            user_id=user.id,
            access_token_hash=self.hash_token(access_token),
            refresh_token_hash=self.hash_token(refresh_token),
            access_expires_at=now + self._access_lifetime,
            refresh_expires_at=now + self._refresh_lifetime,
            revoked_at=None,
        )
        await self._repository.create_session(session)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=session.access_expires_at,
            refresh_expires_at=session.refresh_expires_at,
            user=AuthenticatedUser(id=user.id, email=user.email),
        )

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().casefold()
