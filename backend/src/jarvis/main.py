from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from jarvis.api.auth import router as auth_router
from jarvis.api.health import HealthChecker
from jarvis.api.health import router as health_router
from jarvis.api.router import router as api_router
from jarvis.auth.service import AuthService
from jarvis.core.config import Settings
from jarvis.core.logging import configure_logging
from jarvis.infrastructure.auth_repository import PostgreSQLAuthRepository
from jarvis.infrastructure.database import PostgreSQLHealthChecker
from jarvis.infrastructure.object_storage import S3HealthChecker

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def create_app(
    *,
    settings: Settings | None = None,
    postgresql_health: HealthChecker | None = None,
    s3_health: HealthChecker | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    application_settings = settings or Settings.from_environment()
    configure_logging(application_settings.log_level)

    application = FastAPI(
        title="Jarvis Personal Assistant API",
        version="0.1.0",
        docs_url="/api/docs" if application_settings.environment != "production" else None,
        redoc_url=None,
        openapi_url=(
            "/api/openapi.json" if application_settings.environment != "production" else None
        ),
    )
    application.state.settings = application_settings
    application.state.postgresql_health = postgresql_health or PostgreSQLHealthChecker(
        application_settings
    )
    application.state.s3_health = s3_health or S3HealthChecker(application_settings)
    application.state.auth_service = auth_service or AuthService(
        PostgreSQLAuthRepository(application_settings)
    )

    @application.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_id if _REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid.uuid4())
        )
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    application.include_router(health_router)
    application.include_router(api_router)
    application.include_router(auth_router)
    return application


app = create_app()
