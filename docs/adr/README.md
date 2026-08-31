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
| [ADR-030](ADR-030-observability-collection-and-failure-policy.md) | Accepted | Platform observability collection and failure policy |
| [ADR-029](ADR-029-helm-packaging-and-controlled-migrations.md) | Accepted | Helm packaging and controlled migrations |
| [ADR-028](ADR-028-kubernetes-conformance-ci.md) | Accepted | Kubernetes conformance CI proof |
| [ADR-027](ADR-027-raw-kubernetes-delivery-baseline.md) | Accepted | Raw Kubernetes delivery baseline |
| [ADR-026](ADR-026-media-upload-lifecycle-cleanup.md) | Accepted | Media upload cleanup and Catalog attachment validation |
| [ADR-025](ADR-025-catalog-search-projection.md) | Accepted | Rebuildable Catalog search projection |
| [ADR-024](ADR-024-two-role-order-administration.md) | Accepted | Two-role model and paid-order administration |
| [ADR-023](ADR-023-cart-backed-zarinpal-checkout.md) | Accepted | Cart-backed Zarinpal checkout redirect |
| [ADR-022](ADR-022-zarinpal-payment-adapter-and-expiry.md) | Accepted | Zarinpal payment adapter and expiry |
| [ADR-021](ADR-021-staff-operations-and-customer-order-self-service.md) | Accepted | Staff operations, customer order self-service, and contact-email snapshots |
| [ADR-020](ADR-020-customer-phone-otp-authentication.md) | Accepted | Customer phone OTP authentication and asynchronous SMS delivery |
| [ADR-019](ADR-019-chat-support-queue-assignment.md) | Accepted | Chat support queue assignment |
| [ADR-017](ADR-017-realtime-chat-delivery-and-media-access.md) | Accepted | Realtime Chat delivery and Media access |
| [ADR-016](ADR-016-kafka-consumer-dead-letter-policy.md) | Accepted | Kafka consumer dead-letter policy |
| [ADR-015](ADR-015-invoice-delivery-handoff.md) | Accepted | Durable invoice and notification handoff |
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
| [ADR-014](ADR-014-checkout-saga-and-authoritative-snapshots.md) | Accepted | Checkout Saga and authoritative snapshots |
