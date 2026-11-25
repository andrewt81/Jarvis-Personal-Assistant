"""Guarded, additive upgrade of the verified Jarvis database to revision 0007."""

from __future__ import annotations

import json
import subprocess
import sys

from jarvis.core.config import Settings

BEFORE = "20261022_0006"
TARGET = "20261125_0007"


class MigrationFailure(Exception):
    pass


def migrate(read_state, upgrade, verify_constraints):
    before, table_exists = read_state()
    if before == BEFORE and not table_exists:
        upgrade()
    elif before != TARGET or not table_exists:
        raise MigrationFailure("unexpected_database_revision_or_schema")
    after, exists = read_state()
    if after != TARGET or not exists:
        raise MigrationFailure("migration_revision_not_verified")
    verify_constraints()
    return {
        "ok": True,
        "revision_before": before,
        "revision_after": after,
        "revision_constraints_verified": True,
        "application_containers_restarted": False,
    }


def main():
    try:
        import psycopg

        settings = Settings.from_environment()
        if (
            settings.postgres_host != "10.10.30.20"
            or settings.postgres_port != 5432
            or settings.postgres_database != "jarvis"
            or settings.postgres_user != "jarvis_app"
            or settings.postgres_sslmode != "require"
        ):
            raise MigrationFailure("database_target_configuration_changed")

        def connect():
            return psycopg.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                dbname=settings.postgres_database,
                user=settings.postgres_user,
                password=settings.read_postgres_password(),
                sslmode=settings.postgres_sslmode,
                connect_timeout=5,
                options="-c default_transaction_read_only=on -c statement_timeout=5000",
            )

        def read_state():
            with connect() as connection:
                identity = connection.execute(
                    "SELECT current_database(),current_user,current_schema(),"
                    "(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())"
                ).fetchone()
                if identity != ("jarvis", "jarvis_app", "public", True):
                    raise MigrationFailure("database_identity_or_tls_not_verified")
                rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
                if len(rows) != 1:
                    raise MigrationFailure("unexpected_migration_heads")
                exists = connection.execute(
                    "SELECT to_regclass('public.document_revisions') IS NOT NULL"
                ).fetchone()[0]
                return rows[0][0], exists

        def upgrade():
            result = subprocess.run(  # noqa: S603 - fixed module/arguments, current interpreter
                [sys.executable, "-m", "alembic", "upgrade", TARGET],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                reason = "migration_command_failed"
                if "LockNotAvailable" in result.stderr:
                    reason = "migration_lock_timeout"
                raise MigrationFailure(reason)
            for line in result.stderr.splitlines():
                if line.startswith("INFO  [alembic."):
                    print(line, flush=True)

        def verify_constraints():
            with connect() as connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT conname FROM pg_constraint WHERE conrelid IN "
                        "('public.documents'::regclass,'public.document_revisions'::regclass)"
                    ).fetchall()
                }
            expected = {
                "uq_documents_id_household",
                "document_revisions_pkey",
                "document_revisions_document_id_key",
                "fk_revision_previous_household",
                "fk_revision_document_household",
                "ck_revision_distinct_ids",
            }
            if not expected <= names:
                raise MigrationFailure("revision_constraints_not_verified")

        output = migrate(read_state, upgrade, verify_constraints)
    except MigrationFailure as error:
        output = {"ok": False, "error": str(error)}
    except Exception:
        output = {"ok": False, "error": "migration_or_verification_unavailable"}
    print(json.dumps(output, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
