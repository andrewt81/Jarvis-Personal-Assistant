# Backend deployment contract

The production host already provides `/opt/jarvis/deploy/compose.backend.template.yaml`. This repository does not replace that file.

## Release

1. Run tests and static checks.
2. Build the application image from a verified base-image digest.
3. Record the resulting application-image digest.
4. Validate the production Compose configuration.
5. Run `alembic upgrade head` explicitly with the new image.
6. On the first installation only, create the first owner with the interactive
   `python -m jarvis.cli create-owner` command inside the administrative container context.
7. Update the application image reference to the new digest.
8. Recreate the backend service.
9. Wait for `/health/ready` to return HTTP 200.
10. Run the smoke test.
11. Verify that the existing Traefik `/ping` endpoint still returns HTTP 200.

## Rollback

Restore the previous application-image digest and recreate the service. Database migrations must follow an expand/contract strategy and remain compatible with the previous application release. Do not run an automatic Alembic downgrade during rollback.

## Secrets

- PostgreSQL password: mounted at `/run/secrets/postgresql_password`.
- PostgreSQL non-secret configuration: existing protected env file on the host.
- RustFS credentials and configuration: existing protected env file on the host.
- Never print resolved settings, connection strings, tokens or document content.
