# Invoice and Notification Runbook

## Detection

An Order is `CONFIRMED`, but its Order-owned Invoice remains `PENDING`,
`GENERATING`, or `FAILED`; or Notification delivery remains `PENDING`,
`SENDING`, or `FAILED` beyond the operational threshold.

## Safe checks

1. Check the readiness endpoints for `order-service`, `notification-service`,
   `RabbitMQ`, `MinIO`, and the SMTP provider.
2. In the Order database, inspect only the matching `invoices`,
   `task_intents`, and `outbox_messages` rows. In the Notification database,
   inspect only the matching `inbox_messages`, `notification_deliveries`, and
   `task_intents` rows.
3. Check Kafka consumer lag for `order-invoice-dispatcher` and
   `notification-service`, then inspect the dedicated `order.invoice` and
   `notification.email` queues.
4. Do not query Customer data or edit another service's records to recover the
   workflow.
5. Inspect `fastapi-platform.dead-letter.v1` for a failed Order invoice-dispatch
   or Notification invoice-consumer record.

## Recovery

Restore the unavailable dependency and restart the affected stateless API or
worker. A `PENDING` task intent remains durable until RabbitMQ publisher
confirmation succeeds. A failed Celery task retries with bounded exponential
backoff and jitter. A duplicate task observes the durable Invoice or delivery
state and has no additional durable effect. A processing lease prevents a
concurrent duplicate from entering the external operation; an expired lease is
recoverable by task redelivery.

Do not mark an Invoice as `GENERATED` or an email as `SENT` manually. If SMTP
acceptance is ambiguous, verify provider delivery first: SMTP has no universal
idempotency guarantee, so a recovery retry can create a duplicate email.

For a Kafka poison record, repair the cause and use the [Kafka DLQ runbook](kafka-dlq.md)
instead of manually committing the source offset.

## Verification

Confirm a generated Invoice has an object key, checksum, and size; confirm its
Outbox record is published; confirm one Notification delivery is `SENT`; and
verify the expected message at the configured provider. Local development uses
Mailpit at `http://localhost:8025`.
