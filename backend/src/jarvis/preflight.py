"""Read-only deployment checks. Never create schema, accounts, buckets or objects."""

from __future__ import annotations

import json

from jarvis.core.config import Settings


def _database_engine(settings: Settings):
    from sqlalchemy import create_engine

    return create_engine(
        settings.sqlalchemy_url(),
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )


def _head_bucket(settings: Settings) -> None:
    from jarvis.infrastructure.object_storage import S3HealthChecker

    S3HealthChecker(settings)._check_sync()


def check_postgresql(settings: Settings) -> dict[str, object]:
    if settings.postgres_sslmode not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("TLS must be required")
    engine = _database_engine(settings)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
            row = (
                connection.exec_driver_sql(
                    "SELECT current_database() AS database, current_user AS role, "
                    "COALESCE((SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()), "
                    "false) AS tls, "
                    "has_schema_privilege(current_user, 'public', 'USAGE') AS schema_usage, "
                    "has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create, "
                    "to_regclass('public.alembic_version') IS NOT NULL AS migrations_present"
                )
                .mappings()
                .one()
            )
            if (
                row["database"] != settings.postgres_database
                or row["role"] != settings.postgres_user
                or row["tls"] is not True
            ):
                raise RuntimeError("Unexpected database identity or TLS state")
            return {
                "status": "available",
                "configured_identity_verified": True,
                "tls": True,
                "schema_usage": bool(row["schema_usage"]),
                "schema_create": bool(row["schema_create"]),
                "migrations_present": bool(row["migrations_present"]),
            }
    finally:
        engine.dispose()


def check_storage(settings: Settings) -> dict[str, object]:
    results: dict[str, object] = {"mode": "read_only"}
    for name, operation in (
        ("postgresql", lambda: check_postgresql(settings)),
        ("object_storage", lambda: _head_bucket(settings)),
    ):
        try:
            value = operation()
            results[name] = (
                value
                if value is not None
                else {
                    "status": "available",
                    "head_bucket": True,
                    "object_read_write_permissions": "not_tested",
                }
            )
        except Exception:
            # Deliberately omit exception text, DSNs, credentials and server bodies.
            results[name] = {"status": "unavailable"}
    results["ok"] = all(
        isinstance(results[name], dict) and results[name].get("status") == "available"
        for name in ("postgresql", "object_storage")
    )
    return results


def main() -> int:
    try:
        settings = Settings.from_environment()
    except Exception:
        print(json.dumps({"mode": "read_only", "ok": False, "error": "invalid_configuration"}))
        return 1
    results = check_storage(settings)
    print(json.dumps(results, sort_keys=True))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
