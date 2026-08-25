# Repository Instructions

This repository implements the FastAPI Microservices Platform specification.

## Source of truth

- Treat `docs/architecture/`, accepted ADRs, and canonical artifacts under `contracts/` as the in-repository architecture baseline.
- A material architecture change requires technical justification, an ADR, updated contracts/documentation, and appropriate tests.
- Do not introduce a technology solely to increase stack breadth.

## Mandatory boundaries

- Each microservice owns its business rules, database, migrations, APIs, events, tests, image, and operational behavior.
- Never query or mutate another service's database.
- Never share business/domain models through `libs/`.
- Keep business logic out of FastAPI routes, Kafka consumers, Celery entrypoints, and ORM callbacks.
- Do not keep database transactions open across network calls.

## Communication and durability

- Use REST for synchronous request/response interactions.
- Use Kafka for durable business-domain facts.
- Use RabbitMQ and Celery for directed background work.
- Use Redis only for disposable cache, rate-limit, session/OTP, presence, fan-out, and justified ephemeral coordination state.
- Use S3-compatible object storage for file bytes; PostgreSQL stores metadata.
- Persist critical business state and its outbox record in one local transaction.
- Make Kafka consumers and Celery tasks idempotent.

## Contracts and versions

- Version external APIs from `/api/v1`.
- Version event schemas in event names such as `order.created.v1`.
- Treat API, event, and deployable service versions as independent.
- Do not make a destructive change to an existing event schema.

## Dependency policy

Before installing, downloading, configuring, or pinning a significant dependency, runtime, image, broker, database, CLI, or infrastructure component:

1. Check the official source.
2. Identify the latest stable production-ready release.
3. Read relevant release and migration notes.
4. Verify compatibility with the complete affected stack.
5. Review known security and support-lifecycle issues.
6. Select the latest stable compatible release.
7. Pin or lock it reproducibly.
8. Document the selection and any exception.

Never use remembered versions, stale tutorials, release candidates, unsupported releases, or unbounded `latest` image tags by default.

## Incremental delivery

- Work one approved phase at a time.
- Add tests, documentation, observability, failure behavior, and security evidence with the feature that requires them.
- Do not interpret later observability or hardening phases as permission to defer basic instrumentation or failure testing.
- Keep commits small, coherent, and reviewable.
