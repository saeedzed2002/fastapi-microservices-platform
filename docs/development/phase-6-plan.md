# Phase 6 Plan — Invoice & Notification

## Outcome

Generate a durable Order-owned `PDF` Invoice after checkout confirmation and
deliver its notification through a separate Notification bounded context.

## Scope

- Order records an email contact snapshot at checkout.
- `order.confirmed.v1` creates an Invoice and durable task intent.
- A confirmed RabbitMQ/Celery dispatch generates the `PDF` in S3-compatible
  storage and emits `invoice.generated.v1` through the Order Outbox.
- Notification persists Inbox, delivery, and task intent before sending email.
- Local Compose provides Mailpit only as a development SMTP sink.

## Non-goals

Real SMTP-provider credentials, email attachments, SMS, user-managed templates,
payment receipts, refunds, invoice cancellation, tax rules, invoice downloads,
retention policy automation, and provider-side idempotency are deferred.

## Dependency selection

`ReportLab 5.0.1` was verified on official PyPI on 2026-08-25 as the latest
production-stable BSD-licensed release with Python 3.14 support. `Celery 5.6.3`
and `Boto3 1.43.79` remain the already locked compatible project choices.
Mailpit `v1.30.0` was selected from its official release history for local SMTP
validation; it is not a production mail provider.
