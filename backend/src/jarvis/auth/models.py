from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    password_hash: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class Session:
    id: UUID
    user_id: UUID
    access_token_hash: bytes
    refresh_token_hash: bytes
    access_expires_at: datetime
    refresh_expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    email: str


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: AuthenticatedUser
