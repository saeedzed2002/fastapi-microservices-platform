# Notification Service

Notification owns delivery intents, delivery status, retries, and provider-facing
email execution. It does not own Orders, Invoice bytes, or Customer records.

It consumes `invoice.generated.v1`, atomically records an Inbox entry plus a
delivery intent, then dispatches a durable Celery task. The initial local SMTP
adapter targets Mailpit; production SMTP credentials and provider integration
remain configuration and deployment concerns.
