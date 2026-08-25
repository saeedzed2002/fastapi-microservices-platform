# Checkout Saga Runbook

## Detection

An Order remains in `PENDING`, `INVENTORY_RESERVED`, or `PAYMENT_PENDING` longer
than the agreed operational threshold, or the Outbox backlog rises.

## Safe checks

1. Check each service `/health/ready` endpoint.
2. Inspect the service-owned `outbox_messages` records whose `published_at` is
   null; do not edit payloads or mark messages published manually.
3. Check Kafka consumer-group lag for `order-service`, `inventory-service`, and
   `payment-service`.
4. Inspect the matching `order_id` in only the owning databases, including each
   Inbox record and Inventory reservation.

## Recovery

Restore Kafka connectivity and restart the affected stateless worker or pod.
The Outbox publisher retries unpublished records; consumers write their Inbox
and business effect before committing the Kafka offset. Do not manually replay a
payment or release stock unless the durable records prove normal recovery cannot
complete.

## Verification

Confirm that Outbox records receive `published_at`, consumer lag falls, and the
Order reaches `CONFIRMED` or `CANCELLED`. For `payment.failed.v1`, verify the
Inventory reservation is `RELEASED` and its ledger contains a `release` entry.
