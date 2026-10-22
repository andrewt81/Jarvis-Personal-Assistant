# Backend deployment contract

The production host already provides `/opt/jarvis/deploy/compose.backend.template.yaml`. The
versioned [`deploy/compose.production.yaml`](../../deploy/compose.production.yaml) implements the
same contract and can be compared with that host template before it is installed.

## One-time preparation

1. Make the GHCR package public, or authenticate Docker on the Jarvis host with a read-only token.
2. Copy `deploy/compose.production.yaml` to `/opt/jarvis/deploy/compose.production.yaml`.
3. Copy `deploy/.env.example` to `/opt/jarvis/deploy/release.env`, set the immutable image digest,
   and protect the file with mode `0600`.
4. Set `JARVIS_SECRETS_GID` to the numeric GID returned for the existing `jarvis-secrets` group.
5. Confirm that the external Docker networks `proxy` and `jarvis-app` still exist.

## Release

1. Run tests and static checks.
2. Build the application image from a verified base-image digest.
3. Record the resulting application-image digest.
4. Validate the production Compose configuration with `deploy/verify_release.py`.
5. Run migrations explicitly and separately from startup:

   ```text
   docker compose --env-file /opt/jarvis/deploy/release.env \
     -f /opt/jarvis/deploy/compose.production.yaml run --rm backend alembic upgrade head
   ```
6. On the first installation only, create the first owner with the interactive
   `python -m jarvis.cli create-owner` command inside the administrative container context.
7. Update `JARVIS_IMAGE` in `release.env` to the new digest.
8. Recreate the backend service with `docker compose up --detach --wait backend`.
9. Wait for `/health/ready` to return HTTP 200.
10. Run the smoke test.
11. Verify that the existing Traefik `/ping` endpoint still returns HTTP 200.

## Rollback

Restore the previous application-image digest and recreate the service. Database migrations must follow an expand/contract strategy and remain compatible with the previous application release. Do not run an automatic Alembic downgrade during rollback.

The previous digest must be retained in the release log. Rollback changes only `JARVIS_IMAGE`,
pulls that immutable image and recreates `backend`; it never restores application data from an
unverified snapshot and never performs an automatic schema downgrade.

## Secrets

- PostgreSQL password: mounted at `/run/secrets/postgresql_password`.
- PostgreSQL non-secret configuration: existing protected env file on the host.
- RustFS credentials and configuration: existing protected env file on the host.
- Never print resolved settings, connection strings, tokens or document content.
