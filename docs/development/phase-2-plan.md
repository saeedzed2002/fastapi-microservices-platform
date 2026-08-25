# Phase 2 — Identity and Customer

Phase 2 introduces the first two business bounded contexts while preserving the
database-per-service and event-driven boundaries.

## Delivered

- identity-service with registration, login, refresh rotation, logout, current
  user, health, readiness, and metrics endpoints.
- Argon2id password hashing and short-lived JWT access tokens.
- Opaque refresh sessions with SHA-256 storage, rotation, family tracking, and
  revocation.
- Identity migrations for users, refresh sessions, and the transactional outbox.
- An outbox publisher that emits identity.user_registered.v1 to Kafka with a
  canonical event envelope and aggregate-key ordering.
- customer-service with profile and address ownership, authorization, health,
  readiness, and metrics endpoints.
- Optional Kafka consumer that provisions customer profiles idempotently from the
  identity event.
- Separate PostgreSQL databases and roles for identity and customer in the local
  Compose topology.
- Contract catalog entries, service Dockerfiles, unit tests, and Phase 2 CI.

## Operational commands

From the repository root:

    uv sync --locked --all-packages
    pwsh -File .\scripts\platform.ps1 -Task migrate-identity
    pwsh -File .\scripts\platform.ps1 -Task migrate-customer
    uv run --all-packages pytest

The Kafka publisher and customer consumer are disabled by default for an
infrastructure-free local unit-test run. Enable them only when PostgreSQL and
Kafka are available and the corresponding migrations have been applied.

## Consistency and security notes

- Registration, refresh-session creation, and the identity outbox record commit
  atomically in identity-service.
- Kafka delivery is at least once; customer provisioning is safe to repeat.
- No service queries the other service database.
- The initial HS256 choice is intentionally documented and must be revisited
  before production multi-tenant or multi-issuer deployment.

## Non-goals

OTP, password reset, external identity providers, Redis rate limiting, admin
roles, asymmetric JWKS rotation, mTLS, and production secret management remain
later hardening work. They are not implied by the Phase 2 endpoints.
