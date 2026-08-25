# Architecture Decision Records

ADRs record decisions that materially affect service ownership, contracts, durability, security, deployment, or platform technology.

## Status values

- `Proposed` — under review and not yet authoritative.
- `Accepted` — current architecture baseline.
- `Superseded` — replaced by another ADR; both records remain.
- `Deprecated` — retained temporarily during migration.
- `Rejected` — considered but not selected.

## Process

1. Copy [`template.md`](template.md).
2. Describe the problem and constraints before proposing technology.
3. Record the decision, alternatives, consequences, migration, and validation.
4. Link affected contracts, diagrams, runbooks, and issues.
5. Obtain approval before implementing a material architecture change.
6. Never rewrite decision history to hide an earlier choice; supersede it.

## Index

| ADR | Status | Decision |
|---|---|---|
| [ADR-001](ADR-001-monorepo-and-repository-layout.md) | Accepted | Monorepo and repository layout |
| [ADR-002](ADR-002-service-boundaries-and-database-ownership.md) | Accepted | Bounded contexts and database ownership |
| [ADR-003](ADR-003-synchronous-rest-communication.md) | Accepted | REST for initial synchronous communication |
| [ADR-004](ADR-004-kafka-domain-events.md) | Accepted | Kafka for durable domain events |
| [ADR-005](ADR-005-outbox-inbox-and-idempotency.md) | Accepted | Transactional Outbox, Inbox, and idempotency |
| [ADR-006](ADR-006-rabbitmq-celery-tasks.md) | Accepted | RabbitMQ/Celery for background work |
| [ADR-007](ADR-007-redis-ephemeral-state.md) | Accepted | Redis for ephemeral platform state |
| [ADR-008](ADR-008-s3-compatible-object-storage.md) | Accepted | S3-compatible object storage abstraction |
| [ADR-009](ADR-009-independent-versioning.md) | Accepted | Independent API, event, and service versioning |
| [ADR-010](ADR-010-kubernetes-first-runtime.md) | Accepted | Kubernetes-first application runtime model |
| [ADR-011](ADR-011-identity-token-and-account-lifecycle.md) | Accepted | Identity tokens and account lifecycle |
| [ADR-012](ADR-012-phase-3-media-reference-boundary.md) | Accepted | Media references remain opaque across service boundaries |
| [ADR-013](ADR-013-cart-cache-degradation.md) | Accepted | Cart Redis cache degradation policy |
