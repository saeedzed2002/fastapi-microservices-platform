# Coding Standards

These rules apply when executable code is introduced.

## Architecture

- Keep business logic out of FastAPI routes.
- Routes and workers translate transport input into application use cases.
- Keep domain code independent of FastAPI, SQLAlchemy, Kafka, Celery, Redis, and vendor SDKs.
- Use repository/provider ports where a real boundary exists; do not create interfaces for trivial implementation details.
- Do not import business code or models from another service.
- Do not query another service's database.
- Do not keep a database transaction open during a network call.
- Write critical domain state and its outbox record atomically.
- Make message consumers, background tasks, provider callbacks, and sensitive commands idempotent.

## Python

- Use type annotations for public and application/domain interfaces.
- Treat type checking as a required quality gate; strictness may increase incrementally without normalizing ignored errors.
- Prefer explicit, testable dependencies over module-level mutable clients.
- Use `Decimal` and PostgreSQL `NUMERIC` for money; never binary floating point.
- Store currency explicitly.
- Use timezone-aware UTC timestamps for backend state and contracts.
- Use UUIDs by default for externally visible domain IDs.
- Avoid implicit ORM lazy-loading across application boundaries.
- Use explicit transaction scopes and predictable query behavior.

## API contracts

- Version external endpoints under `/api/v1` from the first implementation.
- Return the canonical error envelope.
- Do not expose stack traces, SQL, table names, raw provider errors, or secrets.
- Standardize pagination and document whether an endpoint uses cursor or offset semantics.
- Validate request and upload size at both edge and service layers.
- Enforce resource ownership and authorization in the service, not only at the gateway.

## Events and tasks

- Event names are past-tense facts ending in `.vN`.
- A breaking event change creates a new event version.
- Preserve `event_id` during publish retry.
- Propagate correlation, causation, and trace context.
- Commit Kafka offsets only after durable consumer effects complete.
- Define queue, acknowledgement, retry, backoff, jitter, maximum attempts, idempotency, and DLQ policy for every Celery task.

## Configuration and secrets

- Use validated environment configuration through Pydantic Settings once selected and pinned.
- Keep business logic environment-independent.
- Commit only placeholder values in `.env.example`.
- Never log, commit, build into images, or publish credentials and tokens.

## Tests and documentation

- Unit-test domain rules and application handlers without infrastructure.
- Integration-test real adapters with real infrastructure where behavior depends on protocol or persistence semantics.
- Validate OpenAPI and event compatibility in CI.
- Add feature-level failure tests with each feature; do not postpone them to hardening.
- Update version-sensitive documentation in the same change as code or configuration.
