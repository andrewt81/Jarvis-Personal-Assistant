# ADR 0003: native Android MVP

- Status: accepted
- Date: 2026-10-22

## Decision

- The Android client is native Kotlin with Jetpack Compose.
- The MVP supports login, automatic session rotation, household selection, the Today task list,
  task completion and PDF/image/text upload through the system document picker.
- Access and refresh tokens are encrypted at rest with an AES-GCM key held by Android Keystore.
- Production traffic is HTTPS-only and defaults to `https://jarvis.tosatto.net`.
- Android 8 (API 26) is the minimum; the target is Android 16 (API 36).
- Gradle, Android Gradle Plugin, Kotlin, Compose BOM and the containerized build SDK are pinned.

## Consequences

The debug APK produced by the main quality gate is installable for private MVP testing. A dedicated
release signing key and Play/internal-distribution policy are required before store distribution;
the signing key must never enter the repository.
