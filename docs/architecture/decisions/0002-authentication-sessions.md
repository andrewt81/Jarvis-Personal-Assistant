# ADR 0002: revocable opaque sessions

- Status: accepted
- Date: 2026-10-22

## Context

Jarvis needs authentication suitable for an Android client, multiple users and immediate
revocation. Introducing signed JWTs would require a new signing secret and would make revocation
dependent on additional state or short expiration periods.

## Decision

- Passwords are hashed with Argon2id and are never logged or returned.
- Access and refresh tokens are cryptographically random opaque values.
- PostgreSQL stores only SHA-256 token hashes.
- Access tokens expire after 15 minutes; refresh tokens expire after 30 days.
- Refresh rotates both tokens atomically. Reuse of a rotated refresh token fails.
- Logout revokes the server-side session immediately.
- The first owner, household and linked person are created through an interactive administrative
  command; there is no public registration endpoint.
- Authentication failures use one generic response to avoid account enumeration.

## Consequences

- Every authenticated request performs a PostgreSQL lookup. This is acceptable for the MVP and
  avoids introducing Redis or another infrastructure component.
- No application signing key needs to be distributed.
- Disabling a user or revoking a session takes effect immediately.
- Rate limiting and security-event audit records remain required before public production use.
