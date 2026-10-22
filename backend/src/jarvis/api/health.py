from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthChecker(Protocol):
    async def check(self) -> None: ...


async def _dependency_state(name: str, checker: HealthChecker) -> tuple[str, str]:
    try:
        await checker.check()
        return name, "available"
    except Exception as error:  # noqa: BLE001 - boundary intentionally sanitizes failures
        logger.warning(
            "Dependency readiness check failed",
            extra={"dependency": name, "error_type": type(error).__name__},
        )
        return name, "unavailable"


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    checks = await asyncio.gather(
        _dependency_state("postgresql", request.app.state.postgresql_health),
        _dependency_state("object_storage", request.app.state.s3_health),
    )
    dependencies = dict(checks)
    is_ready = all(value == "available" for value in dependencies.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "dependencies": dependencies,
        },
    )
