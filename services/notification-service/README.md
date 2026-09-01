# Notification Service

Notification owns delivery intents, delivery status, retries, and provider-facing
email/SMS execution. It does not own Orders, Invoice bytes, Customer records,
or authentication truth.

It consumes `invoice.generated.v1`, atomically records an Inbox entry plus a
delivery intent, then dispatches a durable Celery task. The initial local SMTP
adapter targets Mailpit; production SMTP credentials and provider integration
remain configuration and deployment concerns.

For customer OTP, Identity calls a private authenticated endpoint that records
an `SmsOtpDelivery` plus a `notification.send_otp_sms.v1` task intent in one
local transaction. The RabbitMQ task contains only a delivery ID. The SMS worker
retrieves the still-valid code from Identity immediately before using the
configured `SMS.ir` Bulk adapter; it persists provider acceptance, not carrier
delivery. `NOTIFICATION_SMSIR_*` values and the shared internal secret are
deployment secrets and must never be committed.

## Internal API and operations

Identity invokes `POST /internal/v1/otp-deliveries` and
`POST /internal/v1/password-reset-email-deliveries`. Both require
`X-Platform-Internal-Token`, return `202 Accepted`, and persist the delivery
intent before task dispatch. They are excluded from the public OpenAPI schema.

`GET /health/live`, `GET /health/ready`, and `GET /metrics` are available for
operations. Apply the local schema with
`pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-notification` and
run focused checks with
`uv run --package notification-service pytest services/notification-service/tests -q`.
The API process, Kafka consumer, task dispatcher, and Celery worker have
separate responsibilities; API readiness alone does not prove that queued
deliveries are being consumed or sent.
