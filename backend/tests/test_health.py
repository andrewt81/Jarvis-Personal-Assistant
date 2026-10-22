from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from jarvis.core.config import Settings
from jarvis.main import create_app


class PassingHealthChecker:
    async def check(self) -> None:
        return None


class FailingHealthChecker:
    async def check(self) -> None:
        raise RuntimeError("sensitive dependency detail")


async def get(app, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def settings() -> Settings:
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


def test_liveness_does_not_depend_on_external_services() -> None:
    app = create_app(
        settings=settings(),
        postgresql_health=FailingHealthChecker(),
        s3_health=FailingHealthChecker(),
    )
    response = asyncio.run(get(app, "/health/live"))
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_is_ready_when_dependencies_are_available() -> None:
    app = create_app(
        settings=settings(),
        postgresql_health=PassingHealthChecker(),
        s3_health=PassingHealthChecker(),
    )
    response = asyncio.run(get(app, "/health/ready"))
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"postgresql": "available", "object_storage": "available"},
    }


def test_readiness_sanitizes_dependency_failures() -> None:
    app = create_app(
        settings=settings(),
        postgresql_health=PassingHealthChecker(),
        s3_health=FailingHealthChecker(),
    )
    response = asyncio.run(get(app, "/health/ready"))
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"postgresql": "available", "object_storage": "unavailable"},
    }
    assert "sensitive dependency detail" not in response.text


def test_version_endpoint() -> None:
    app = create_app(
        settings=settings(),
        postgresql_health=PassingHealthChecker(),
        s3_health=PassingHealthChecker(),
    )
    response = asyncio.run(get(app, "/api/v1/version"))
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"
