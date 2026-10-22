# ADR 0001: backend stack

Status: proposed for the first executable milestone.

## Context

Jarvis needs a stateless HTTP backend, PostgreSQL, S3-compatible document storage and later OCR/AI processing. The deployed infrastructure already mandates Docker, port 8080, explicit health endpoints and non-privileged execution.

## Decision

Use Python 3.12, FastAPI, SQLAlchemy, psycopg, Alembic and the standard S3 API through boto3.

Do not introduce Redis, a message broker or another database. If asynchronous document processing becomes necessary, first use a PostgreSQL-backed job table and a worker based on the same application image. Adding that worker requires a separate reviewed decision.

## Consequences

- OCR and AI libraries can be integrated without adding another language runtime.
- OpenAPI is generated from the HTTP application.
- Database changes remain explicit and versioned.
- The application remains portable from RustFS to another S3-compatible provider.
- Python dependency versions and container images must be locked before production deployment.
