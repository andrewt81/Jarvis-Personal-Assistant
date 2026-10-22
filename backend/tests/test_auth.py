from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from jarvis.auth.models import Session, User
from jarvis.auth.passwords import PasswordManager
from jarvis.auth.rate_limit import AuthenticationRateLimiter, RateLimit
from jarvis.auth.service import AuthService, InvalidSessionError
from jarvis.core.config import Settings
from jarvis.main import create_app


class InMemoryAuthRepository:
    def __init__(self, user: User) -> None:
        self.users = {user.id: user}
        self.sessions: dict[UUID, Session] = {}
        self.security_events: list[tuple[str, UUID | None, bytes | None]] = []

    async def find_user_by_email(self, email: str) -> User | None:
        return next((user for user in self.users.values() if user.email == email), None)

    async def find_user_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def update_password_hash(self, user_id: UUID, password_hash: str) -> None:
        self.users[user_id] = replace(self.users[user_id], password_hash=password_hash)

    async def create_session(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def find_session_by_access_hash(self, token_hash: bytes) -> Session | None:
        return next(
            (
                session
                for session in self.sessions.values()
                if session.access_token_hash == token_hash
            ),
            None,
        )

    async def find_session_by_refresh_hash(self, token_hash: bytes) -> Session | None:
        return next(
            (
                session
                for session in self.sessions.values()
                if session.refresh_token_hash == token_hash
            ),
            None,
        )

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
        session = self.sessions[session_id]
        if session.revoked_at is not None:
            return False
        if session.refresh_token_hash != expected_refresh_token_hash:
            return False
        self.sessions[session_id] = replace(
            session,
            access_token_hash=access_token_hash,
            refresh_token_hash=refresh_token_hash,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )
        return True

    async def revoke_session(self, session_id: UUID, revoked_at: datetime) -> None:
        self.sessions[session_id] = replace(self.sessions[session_id], revoked_at=revoked_at)

    async def record_security_event(
        self,
        event_type: str,
        *,
        user_id: UUID | None = None,
        subject_hash: bytes | None = None,
    ) -> None:
        self.security_events.append((event_type, user_id, subject_hash))

    def create_first_owner(
        self,
        *,
        email: str,
        password_hash: str,
        household_name: str,
        display_name: str,
    ) -> UUID:
        raise NotImplementedError


class PassingHealthChecker:
    async def check(self) -> None:
        return None


def test_login_refresh_and_logout_rotate_and_revoke_tokens() -> None:
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    passwords = PasswordManager()
    user = User(
        id=uuid4(),
        email="marco@example.test",
        password_hash=passwords.hash("correct horse battery staple"),
        is_active=True,
    )
    repository = InMemoryAuthRepository(user)
    service = AuthService(repository, password_manager=passwords, now=lambda: now)

    pair = asyncio.run(service.login("  Marco@Example.Test ", "correct horse battery staple"))
    assert pair.access_token != pair.refresh_token
    stored_session = next(iter(repository.sessions.values()))
    assert stored_session.access_token_hash == AuthService.hash_token(pair.access_token)
    assert stored_session.access_token_hash != pair.access_token.encode()
    assert asyncio.run(service.authenticate(pair.access_token)).id == user.id

    rotated = asyncio.run(service.refresh(pair.refresh_token))
    assert rotated.access_token != pair.access_token
    assert rotated.refresh_token != pair.refresh_token
    try:
        asyncio.run(service.authenticate(pair.access_token))
    except InvalidSessionError:
        pass
    else:
        raise AssertionError("Rotated access token remained valid")

    asyncio.run(service.logout(rotated.access_token))
    try:
        asyncio.run(service.authenticate(rotated.access_token))
    except InvalidSessionError:
        pass
    else:
        raise AssertionError("Revoked access token remained valid")
    assert [event[0] for event in repository.security_events] == [
        "authentication.login.succeeded",
        "authentication.refresh.succeeded",
        "authentication.logout.succeeded",
    ]


def test_auth_api_does_not_reveal_which_credential_failed() -> None:
    passwords = PasswordManager()
    user = User(
        id=uuid4(),
        email="marco@example.test",
        password_hash=passwords.hash("correct horse battery staple"),
        is_active=True,
    )
    service = AuthService(InMemoryAuthRepository(user), password_manager=passwords)
    app = create_app(
        settings=_settings(),
        postgresql_health=PassingHealthChecker(),
        s3_health=PassingHealthChecker(),
        auth_service=service,
    )

    wrong_password = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": user.email, "password": "incorrect"},
        )
    )
    missing_user = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": "missing@example.test", "password": "incorrect"},
        )
    )
    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert wrong_password.json() == missing_user.json()


def test_auth_api_login_me_refresh_and_logout() -> None:
    passwords = PasswordManager()
    user = User(
        id=uuid4(),
        email="marco@example.test",
        password_hash=passwords.hash("correct horse battery staple"),
        is_active=True,
    )
    service = AuthService(InMemoryAuthRepository(user), password_manager=passwords)
    app = create_app(
        settings=_settings(),
        postgresql_health=PassingHealthChecker(),
        s3_health=PassingHealthChecker(),
        auth_service=service,
    )

    login = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": user.email, "password": "correct horse battery staple"},
        )
    )
    assert login.status_code == 200
    tokens = login.json()
    me = asyncio.run(
        _request(
            app,
            "GET",
            "/api/v1/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    )
    assert me.json() == {"id": str(user.id), "email": user.email}

    refresh = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
    )
    assert refresh.status_code == 200
    rotated = refresh.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]

    logout = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )
    )
    assert logout.status_code == 204
    rejected = asyncio.run(
        _request(
            app,
            "GET",
            "/api/v1/me",
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )
    )
    assert rejected.status_code == 401


def test_auth_api_limits_repeated_failed_logins() -> None:
    passwords = PasswordManager()
    user = User(
        id=uuid4(),
        email="marco@example.test",
        password_hash=passwords.hash("correct horse battery staple"),
        is_active=True,
    )
    service = AuthService(InMemoryAuthRepository(user), password_manager=passwords)
    limiter = AuthenticationRateLimiter(
        client_limit=RateLimit(1, 60),
        account_limit=RateLimit(1, 60),
    )
    app = create_app(
        settings=_settings(),
        postgresql_health=PassingHealthChecker(),
        s3_health=PassingHealthChecker(),
        auth_service=service,
        authentication_rate_limiter=limiter,
    )

    first = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": user.email, "password": "incorrect"},
        )
    )
    limited = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": user.email, "password": "incorrect"},
        )
    )

    assert first.status_code == 401
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


async def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def _settings() -> Settings:
    return Settings(
        environment="test",
        http_host="127.0.0.1",
        http_port=8080,
        log_level="WARNING",
        postgres_host="postgres",
        postgres_port=5432,
        postgres_database="jarvis",
        postgres_user="jarvis_app",
        postgres_sslmode="require",
        postgres_password_file=Path("/not-used"),
        s3_endpoint_url="http://rustfs:9000",
        s3_bucket="jarvis-documents-test",
        s3_region="us-east-1",
        s3_path_style=True,
        s3_access_key_id="not-used",
        s3_secret_access_key="not-" + "used",
    )
