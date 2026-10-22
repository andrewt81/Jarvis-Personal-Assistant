from __future__ import annotations

import asyncio
import os

import pytest
from jarvis.auth.passwords import PasswordManager
from jarvis.auth.service import AuthService, InvalidSessionError
from jarvis.core.config import Settings
from jarvis.infrastructure.auth_repository import PostgreSQLAuthRepository
from sqlalchemy import text


@pytest.mark.integration
def test_authentication_lifecycle_against_postgresql() -> None:
    if os.environ.get("JARVIS_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("PostgreSQL integration test is opt-in")

    settings = Settings.from_environment()
    repository = PostgreSQLAuthRepository(settings)
    passwords = PasswordManager()
    with repository._engine().begin() as connection:
        connection.execute(
            text("TRUNCATE auth_sessions, people, household_memberships, households, users CASCADE")
        )

    user_id = repository.create_first_owner(
        email="integration@example.test",
        password_hash=passwords.hash("correct horse battery staple"),
        household_name="Integration household",
        display_name="Integration owner",
    )
    service = AuthService(repository, password_manager=passwords)
    pair = asyncio.run(service.login("integration@example.test", "correct horse battery staple"))
    assert pair.user.id == user_id
    assert asyncio.run(service.authenticate(pair.access_token)).id == user_id

    rotated = asyncio.run(service.refresh(pair.refresh_token))
    with pytest.raises(InvalidSessionError):
        asyncio.run(service.authenticate(pair.access_token))
    asyncio.run(service.logout(rotated.access_token))
    with pytest.raises(InvalidSessionError):
        asyncio.run(service.authenticate(rotated.access_token))

    with repository._engine().begin() as connection:
        stored = connection.execute(
            text("SELECT access_token_hash, refresh_token_hash FROM auth_sessions")
        ).one()
        assert bytes(stored.access_token_hash) != rotated.access_token.encode()
        assert bytes(stored.refresh_token_hash) != rotated.refresh_token.encode()
