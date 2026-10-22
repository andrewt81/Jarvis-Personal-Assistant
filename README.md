# Jarvis Personal Assistant

Backend and Android application for Jarvis Personal Assistant.

The evolving product scope, decisions, progress log and MVP roadmap are maintained in
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

Development follows the `develop` -> `main` promotion model documented in
[`CONTRIBUTING.md`](CONTRIBUTING.md). The `main` branch represents production.

The repository is currently in its first backend milestone. The implemented surface is deliberately small:

- process liveness;
- dependency readiness for PostgreSQL and S3-compatible storage;
- application version endpoint;
- initial multi-user database migration;
- container and deployment contracts compatible with the existing Jarvis infrastructure.

## Local backend

Create a virtual environment, install the project with development dependencies, then run:

```text
uvicorn jarvis.main:app --host 0.0.0.0 --port 8080
```

The production container installs the exact runtime versions recorded in
`requirements.lock`. Dependency upgrades are deliberate changes and must be followed by the
complete test suite.

Production secrets must never be copied into this repository. The PostgreSQL password is read from a mounted file. S3 credentials are provided through the protected environment file already present on the server.

## Tests

```text
pytest
```

## Database migrations

Migrations are explicit and separate from normal application startup:

```text
alembic upgrade head
```

## First owner and authentication

After applying migrations, create the first owner from an interactive administrative shell:

```text
python -m jarvis.cli create-owner --email marco@example.com --household "Famiglia" --display-name "Marco"
```

The password is requested without echo and never accepted as a command-line argument. Public API
registration remains disabled. Authentication endpoints are available under `/api/v1/auth`, and
`GET /api/v1/me` validates the current bearer session.

Authenticated users can list their households with `GET /api/v1/households`. Household members
can read profiles under `GET /api/v1/households/{household_id}/people`; owners and adults can
create or update them. Every lookup verifies membership server-side and hides resources belonging
to another household.

Owners and adults can upload private PDF, text and image originals (up to 25 MiB) through the
authenticated household document API. PostgreSQL stores metadata and SHA-256 hashes; RustFS stores
the bytes under a household-scoped key. Downloads are proxied by the backend after authorization,
so the private RustFS endpoint is never exposed to Android clients.

## Infrastructure contract

The backend:

- listens on `0.0.0.0:8080`;
- does not publish host ports directly;
- runs as a non-root user;
- supports a read-only root filesystem and writable `/tmp` tmpfs;
- writes structured logs to stdout/stderr;
- handles `SIGTERM` through the ASGI server;
- exposes `/health/live` and `/health/ready`;
- stores structured data in PostgreSQL and persistent files in S3-compatible storage.

## Android MVP

The native Kotlin/Compose client lives in `android/`. It defaults to
`https://jarvis.tosatto.net` and can be built reproducibly with:

```text
cd android
./gradlew :app:assembleDebug
```

The resulting private-test APK is `android/app/build/outputs/apk/debug/app-debug.apk`. Every
successful update to `main` also publishes it as a GitHub Actions artifact. Tokens are encrypted
with Android Keystore; cleartext network traffic and Android cloud backup are disabled.
