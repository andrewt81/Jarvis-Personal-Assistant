from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

MembershipRole = Literal["owner", "adult", "viewer"]
PersonKind = Literal["adult", "child", "other"]


@dataclass(frozen=True, slots=True)
class Household:
    id: UUID
    name: str
    role: MembershipRole
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Membership:
    household_id: UUID
    user_id: UUID
    role: MembershipRole


@dataclass(frozen=True, slots=True)
class Person:
    id: UUID
    household_id: UUID
    display_name: str
    kind: PersonKind
    linked_user_id: UUID | None
    created_at: datetime
