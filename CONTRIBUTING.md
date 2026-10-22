# Contributing

## Branch model

- `main` contains the production-ready version.
- `develop` contains features that have been integrated but are not yet promoted to
  production.
- New work starts from `develop` in a short-lived branch such as `feature/<name>`,
  `fix/<name>` or `docs/<name>`.
- Feature branches are merged into `develop` after local verification.
- A release is promoted through a pull request from `develop` to `main`.
- Hotfixes start from `main`, return to `main` through a pull request and are then brought
  back into `develop`.

Do not push feature work directly to `main`. Keep pull requests small and include tests for
behavioural changes.

## GitHub Actions

The quality workflow is intentionally limited to:

- pull requests whose target branch is `main`;
- updates to `main`, including completed merges.

Pushes to `develop` and feature branches do not start GitHub Actions. Local tests and checks
remain required before merging into `develop`.

## Required local checks

```text
python -m ruff check .
python -m ruff format --check .
python -m pytest
docker build --file docker/backend.Dockerfile --tag jarvis-personal-assistant:local .
```
