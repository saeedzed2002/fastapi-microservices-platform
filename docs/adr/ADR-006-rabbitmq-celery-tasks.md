# ADR-006 — Use RabbitMQ and Celery for directed background work

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Email, SMS, invoice generation, image processing, cleanup, and maintenance are executable work with retry and worker-scaling needs. They are not immutable domain facts and must not block HTTP requests.

## Decision

Use RabbitMQ as the task broker and Celery as the distributed task execution system. Workers and queues are owned by bounded context and workload rather than one global worker.

Every task defines idempotency, acknowledgement timing, retryable exceptions, exponential backoff, jitter, maximum attempts, time limits, poison-task handling, and recovery ownership. Durable or important work does not use FastAPI `BackgroundTasks`.

Before a critical Kafka-to-RabbitMQ workflow is implemented, define a durable task-dispatch protocol that closes the consumer/task dual-write gap.

## Consequences

### Positive

- Background work scales and fails independently of APIs.
- Workload-specific queues isolate slow or resource-intensive tasks.
- Retry and scheduling behavior is explicit.

### Negative and risks

- External side effects can occur before status persistence and therefore require idempotency.
- Broker-to-database/task handoff adds another durability boundary.
- Poison tasks and retry storms require operational limits and DLQs.

## Alternatives considered

- FastAPI `BackgroundTasks`: rejected for durable or important work.
- Kafka as a task queue: rejected because business facts and directed work have different semantics.
- One global Celery worker: rejected because it couples bounded contexts and workloads.

## Compatibility and migration

No critical Kafka-to-RabbitMQ path may ship until the first consuming phase records and validates the durable dispatch protocol. Queue names, task payload versions, acknowledgement mode, and worker rollout must support old and new workers concurrently; incompatible task changes use a new task name or queue and a controlled drain.

## Validation

- Integration tests cover broker outage, late acknowledgement, worker crash, retry exhaustion, and DLQ replay.
- Duplicate execution cannot duplicate invoice, media, email, or provider effects.
- Metrics expose queue depth, unacknowledged work, retries, failures, and duration.

## Related material

- [Communication and consistency](../architecture/communication-and-consistency.md)
- [Media and invoice flows](../diagrams/media-and-invoice.md)
- [Runbooks index](../runbooks/README.md)
