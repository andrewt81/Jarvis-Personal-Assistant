from __future__ import annotations

import asyncio

import boto3
from botocore.config import Config

from jarvis.core.config import Settings


class S3HealthChecker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self) -> None:
        await asyncio.wait_for(asyncio.to_thread(self._check_sync), timeout=4.0)

    def _check_sync(self) -> None:
        settings = self._settings
        if not settings.s3_configured:
            raise RuntimeError("S3 configuration is incomplete")
        addressing_style = "path" if settings.s3_path_style else "virtual"
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=2,
                read_timeout=2,
                retries={"max_attempts": 1, "mode": "standard"},
                s3={"addressing_style": addressing_style},
            ),
        )
        client.head_bucket(Bucket=settings.s3_bucket)
