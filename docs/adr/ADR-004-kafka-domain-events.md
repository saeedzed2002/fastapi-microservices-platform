# ADR-004 — Use Kafka for durable domain events

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Independent bounded contexts need durable facts, fan-out, replay, projection rebuilding, and eventual consistency without direct database coupling.

## Decision

Use Apache Kafka for versioned business-domain events answering “what happened?”. Organize initial topics by bounded context under the `fastapi-platform` namespace. Use a stable aggregate or documented workflow key where partition-local ordering matters.

Each consuming service owns a consumer group; replicas of that service share it where appropriate. Treat delivery as at least once. Use the canonical event envelope, explicit schema versions, idempotent consumers, finite retries, consumer-owned failure handling, and inspectable DLQs.

Redis Pub/Sub and RabbitMQ task queues cannot transport critical domain events as their primary mechanism.

## Consequences

### Positive

- Durable, replayable integration history.
- Independent consumers and rebuildable projections.
- Producer availability is decoupled from consumer processing.

### Negative and risks

- Ordering is partition-local, not global.
- Retention and replay require version-compatible consumers.
- Consumer lag, poison events, and schema evolution add operational work.

## Alternatives considered

- Redis Pub/Sub: rejected for critical facts because delivery is ephemeral.
- RabbitMQ tasks: rejected as an event log because tasks express directed work.
- Direct synchronous fan-out: rejected because it couples producer availability to every consumer.

## Compatibility and migration

Reserved event names are not production contracts until a payload schema and compatibility gate are active. Additive compatible changes preserve the event version; breaking payload semantics create a new event type version and a dual-consume or dual-publish migration window. Topic migration is handled separately.

## Validation

- Contract tests validate envelopes and payload compatibility.
- Integration tests cover replay, duplicate delivery, lag, retry, and DLQ behavior.
- Metrics expose production, consumption, processing failures, and lag.

## Related material

- [Event contracts](../../contracts/events/README.md)
- [Communication and consistency](../architecture/communication-and-consistency.md)
- [Checkout Saga](../diagrams/checkout-saga.md)
