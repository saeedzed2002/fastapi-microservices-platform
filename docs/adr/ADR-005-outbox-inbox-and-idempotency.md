# ADR-005 — Require Transactional Outbox, Inbox, and idempotency

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

A database commit followed by broker publication has a dual-write failure window. Kafka may also redeliver an event, and an external provider may repeat the same semantic fact under a different delivery ID.

## Decision

Write critical business state and its outbox record in the same service-owned PostgreSQL transaction. Publish asynchronously and mark the record published only after broker acknowledgement.

Consumers atomically insert an Inbox record, apply conditional business effects, and write resulting outbox records in one local transaction before committing the Kafka offset.

Inbox event-ID deduplication is supplemented by domain state guards, unique business keys, API idempotency keys, and provider idempotency where required.

## Consequences

### Positive

- A broker outage after a database commit cannot lose the event intent.
- Duplicate delivery does not duplicate business effects.
- Failure and recovery state is inspectable.

### Negative and risks

- Publishers and consumers require additional tables and cleanup policy.
- Publish-then-crash still creates duplicates by design.
- Polling, row claiming, ordering, retry, retention, and backlog operations need careful implementation.

## Alternatives considered

- Direct commit then publish: rejected because committed state can become invisible to consumers.
- Distributed two-phase commit: rejected because the platform does not require or assume distributed ACID.
- Kafka transport exactly-once claims without business idempotency: rejected because external effects and databases remain separate boundaries.

## Compatibility and migration

Outbox and Inbox tables are introduced through service-owned additive migrations before any critical event flow is enabled. Producers and consumers must tolerate mixed deployment revisions during rolling rollout. Retention, partitioning, and cleanup changes require backward-compatible migrations and an operational runbook.

## Validation

- Kill Kafka after a business commit and verify later publication.
- Crash a publisher after broker acceptance and verify duplicate-safe consumption.
- Deliver payment success twice and verify one confirmation and one downstream event.
- Alert on outbox age/backlog and Inbox failures.

## Related material

- [Transactional Outbox and Inbox diagram](../diagrams/outbox-inbox.md)
- [Communication and consistency](../architecture/communication-and-consistency.md)
- [Runbooks index](../runbooks/README.md)
