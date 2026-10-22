from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, text

from jarvis.core.config import Settings


class PostgreSQLHealthChecker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self) -> None:
        await asyncio.wait_for(asyncio.to_thread(self._check_sync), timeout=4.0)

    def _check_sync(self) -> None:
        engine = create_engine(
            self._settings.sqlalchemy_url(),
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            connect_args={"connect_timeout": 3},
        )
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()
