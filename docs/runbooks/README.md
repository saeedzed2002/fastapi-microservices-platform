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
