# ADR-015: Durable invoice and notification handoff

- Status: Accepted
- Date: 2026-08-25

## Context

Generating an invoice and sending its email are directed, retryable work. The
workflow crosses Kafka, PostgreSQL, RabbitMQ, Celery, object storage, and SMTP.
Publishing a task directly from a Kafka consumer would create an untracked
dual-write failure window. Notification must not query Customer or Order data.

## Decision

Order consumes its durable `order.confirmed.v1` fact with an independent Kafka
consumer group. In one local transaction it records the Inbox fact, creates one
Invoice and one `TaskIntent`. The dispatcher claims a pending or lease-expired
intent with `FOR UPDATE SKIP LOCKED`, records `DISPATCHING` together with a
unique claim token and lease timestamp, publishes a confirmed Celery message,
then records `DISPATCHED` only when it still owns that claim. An uncertain
publish result may produce a duplicate task; the Invoice order uniqueness and
deterministic object key make the worker idempotent.

The Invoice worker renders a `PDF` from immutable Order items, writes it to the
Order-owned S3-compatible bucket, persists invoice metadata, then adds
`invoice.generated.v1` to the Order Outbox in one transaction. The Invoice
event includes the checkout-time email contact snapshot, tracking code, and
invoice identifier. This limited PII transfer excludes invoice bytes and
addresses.

Notification consumes that fact, records its own Inbox plus one delivery and
TaskIntent in one transaction, and uses a separate Celery queue to send email.
The initial local SMTP endpoint is Mailpit. Production SMTP credentials and
provider idempotency remain external configuration.

## Consequences

### Positive

- Each business context keeps a local durability boundary and no service reads
  another service database.
- RabbitMQ unavailability leaves a recoverable pending task intent rather than
  losing work.
- A dispatcher crash after claim is recoverable after the bounded claim lease;
  an older dispatcher cannot overwrite a reclaimed task's state.
- Repeated Kafka or Celery delivery cannot create a second Invoice or delivery.

### Negative and risks

- A broker confirmation/database-mark race can execute a task more than once;
  workers must remain idempotent.
- An SMTP server can accept a message before the delivery row is updated, so a
  retry may send a duplicate without a provider-side idempotency feature.
- Contact snapshots are PII and require retention and log-scrubbing controls.

## Alternatives considered

- Sending email in the Kafka handler: rejected because a broker or SMTP failure
  would block consumption or lose the directed work.
- Notification querying Customer or Order tables: rejected because it violates
  service ownership.
- Using Kafka as the task queue: rejected because task retry and worker routing
  have RabbitMQ/Celery semantics.

## Compatibility and migration

`invoice.generated.v1` is immutable. New delivery fields require optional
additions or a new event version. Queue and task names are versioned; breaking
task payload changes use a new task name and controlled drain. Existing Orders
without an email snapshot receive an Invoice but do not emit the delivery event.

## Validation

- Unit tests cover `PDF` output, legal Order transitions, and event contracts.
- Integration tests validate migrations, Inbox deduplication, pending task
  recovery, object upload, and Mailpit SMTP delivery.
- End-to-end validation confirms one confirmed Order produces one Invoice and
  one email; duplicate event/task delivery does not create extra durable rows.

## Related material

- [Media and invoice flows](../diagrams/media-and-invoice.md)
- [RabbitMQ and Celery decision](ADR-006-rabbitmq-celery-tasks.md)
- [Object storage decision](ADR-008-s3-compatible-object-storage.md)
