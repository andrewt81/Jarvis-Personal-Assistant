from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus


def _first(environment: Mapping[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = environment.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    http_host: str
    http_port: int
    log_level: str
    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_user: str
    postgres_sslmode: str
    postgres_password_file: Path
    s3_endpoint_url: str
    s3_bucket: str
    s3_region: str
    s3_path_style: bool
    s3_access_key_id: str = field(repr=False)
    s3_secret_access_key: str = field(repr=False)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environment is None else environment
        return cls(
            environment=_first(env, "JARVIS_ENVIRONMENT", default="development"),
            # The container must accept traffic from Traefik on the Docker proxy network.
            http_host=_first(env, "JARVIS_HTTP_HOST", default="0.0.0.0"),  # noqa: S104
            http_port=int(_first(env, "JARVIS_HTTP_PORT", default="8080")),
            log_level=_first(env, "JARVIS_LOG_LEVEL", default="INFO").upper(),
            postgres_host=_first(env, "JARVIS_POSTGRES_HOST", "POSTGRES_HOST", "PGHOST"),
            postgres_port=int(
                _first(env, "JARVIS_POSTGRES_PORT", "POSTGRES_PORT", "PGPORT", default="5432")
            ),
            postgres_database=_first(env, "JARVIS_POSTGRES_DATABASE", "POSTGRES_DB", "PGDATABASE"),
            postgres_user=_first(env, "JARVIS_POSTGRES_USER", "POSTGRES_USER", "PGUSER"),
            postgres_sslmode=_first(
                env, "JARVIS_POSTGRES_SSLMODE", "POSTGRES_SSLMODE", "PGSSLMODE", default="require"
            ),
            postgres_password_file=Path(
                _first(
                    env,
                    "JARVIS_POSTGRES_PASSWORD_FILE",
                    "POSTGRES_PASSWORD_FILE",
                    "PGPASSWORD_FILE",
                    default="/run/secrets/postgresql_password",
                )
            ),
            s3_endpoint_url=_first(
                env, "JARVIS_S3_ENDPOINT_URL", "S3_ENDPOINT_URL", "RUSTFS_ENDPOINT"
            ),
            s3_bucket=_first(env, "JARVIS_S3_BUCKET", "S3_BUCKET", "RUSTFS_BUCKET"),
            s3_region=_first(
                env, "JARVIS_S3_REGION", "S3_REGION", "AWS_DEFAULT_REGION", default="us-east-1"
            ),
            s3_path_style=_as_bool(
                _first(
                    env,
                    "JARVIS_S3_PATH_STYLE",
                    "S3_PATH_STYLE",
                    "RUSTFS_PATH_STYLE",
                    default="true",
                )
            ),
            s3_access_key_id=_first(
                env,
                "JARVIS_S3_ACCESS_KEY_ID",
                "S3_ACCESS_KEY_ID",
                "AWS_ACCESS_KEY_ID",
                "RUSTFS_ACCESS_KEY",
            ),
            s3_secret_access_key=_first(
                env,
                "JARVIS_S3_SECRET_ACCESS_KEY",
                "S3_SECRET_ACCESS_KEY",
                "AWS_SECRET_ACCESS_KEY",
                "RUSTFS_SECRET_KEY",
            ),
        )

    @property
    def postgres_configured(self) -> bool:
        return all(
            (
                self.postgres_host,
                self.postgres_database,
                self.postgres_user,
                str(self.postgres_password_file),
            )
        )

    @property
    def s3_configured(self) -> bool:
        return all(
            (
                self.s3_endpoint_url,
                self.s3_bucket,
                self.s3_access_key_id,
                self.s3_secret_access_key,
            )
        )

    def read_postgres_password(self) -> str:
        password = self.postgres_password_file.read_text(encoding="utf-8").strip()
        if not password:
            raise RuntimeError("PostgreSQL password file is empty")
        return password

    def sqlalchemy_url(self) -> str:
        if not self.postgres_configured:
            raise RuntimeError("PostgreSQL configuration is incomplete")
        password = quote_plus(self.read_postgres_password())
        user = quote_plus(self.postgres_user)
        database = quote_plus(self.postgres_database)
        return (
            f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:"
            f"{self.postgres_port}/{database}?sslmode={quote_plus(self.postgres_sslmode)}"
        )
