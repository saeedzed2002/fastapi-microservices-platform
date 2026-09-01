# Runbooks

Runbooks are added with the infrastructure and failure condition they operate. Each runbook includes detection, impact, immediate checks, safe mitigation, recovery, verification, escalation, and follow-up.

Required initial runbook topics include:

- Kafka consumer lag is increasing.
- Outbox backlog is increasing.
- RabbitMQ queue depth or unacknowledged work is increasing.
- Celery retry/failure rate is high.
- Redis is unavailable.
- Database pool is exhausted.
- Chat connections are dropping.
- Object storage is unavailable.
- A DLQ requires inspection and replay.
- A migration or rollout failed.

Phase 0 reserves these operational obligations; runnable commands and thresholds are added only after the corresponding implementation exists.

Implemented: [Kafka dead-letter inspection and replay](kafka-dlq.md),
[observability collection and alert response](observability.md),
[resilience disruption and recovery](resilience-recovery.md),
[checkout and invoice recovery](checkout-saga.md),
[invoice and notification recovery](invoice-notification.md), and
[Chat realtime delivery and attachment access](chat-realtime.md), and
[SMS.ir customer OTP delivery](sms-otp.md), and
[staff operations and order review](admin-operations.md), and
[Zarinpal payment recovery](zarinpal-payment.md), and
[local Zarinpal sandbox checkout](local-zarinpal-sandbox-test.md), and
[Catalog category administration](catalog-category-administration.md), and
[Catalog product review moderation](catalog-review-moderation.md), and
[Kubernetes API autoscaling](kubernetes-autoscaling.md), and
[online payment provider routing](online-payment-provider-routing.md), and
[post-delivery return reconciliation](post-delivery-returns.md).
