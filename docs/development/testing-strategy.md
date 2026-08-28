# Testing Strategy

Testing is part of implementation and Definition of Done, not a final cleanup phase.

## Unit tests

Run without real infrastructure and focus on:

- entities, value objects, policies, and invariants;
- state-machine transitions;
- application handlers;
- Saga reactions and compensations;
- idempotency decisions;
- serialization/validation rules that do not require a broker.

## Integration tests

Use real dependencies in isolated containers where protocol or persistence behavior matters:

- PostgreSQL transactions, migrations, locks, Outbox, and Inbox;
- Kafka publication, consumption, keys, replay, duplicate delivery, and DLQ behavior;
- RabbitMQ/Celery acknowledgement, retry, worker loss, and task idempotency;
- Redis cache, rate limit, presence, and fan-out behavior;
- MinIO/S3 presigning, verification, processing, outage, and cleanup.

Testcontainers is the preferred candidate when its current stable toolchain is verified. Mocks do not replace all infrastructure tests.

## Contract tests

- Validate exported OpenAPI documents and canonical error responses.
- Validate event envelopes and payload schemas.
- Detect removed/renamed required fields, incompatible types, endpoint removal, and other breaking changes.
- Verify producer examples and consumer fixtures against the same canonical schema.
- Test supported coexistence during version migration.

## End-to-end tests

Checkout eventually covers registration, product creation, stock, cart, order snapshot, reservation, payment, confirmation, invoice generation, object upload, and notification completion.

Chat covers two authenticated users, membership, database commit before ACK, realtime delivery, reconnect catch-up, deduplication, attachments, and later multi-pod fan-out. Edge coverage proves HTTPS routing, redirect, headers, basic rate limits, blocked internal paths, no direct API host port, and Chat WebSocket upgrades.

Asynchronous tests use bounded polling of observable state. Fixed sleeps are avoided. Tests isolate identifiers, clean data, control time where possible, and report which stage failed.

## Failure and resilience tests

Add relevant cases with each feature:

- Kafka unavailable after database commit;
- duplicate Kafka event;
- duplicate payment success;
- RabbitMQ unavailable during task dispatch;
- SMTP failure;
- Redis failure during Chat and security-sensitive operations;
- Celery worker crash after external or storage side effects;
- object-storage outage and incomplete upload;
- pod termination during HTTP, Kafka, Celery, or WebSocket work;
- timeout and late Saga events.

Safe behavior means durable truth is preserved, repeated effects are prevented, degradation is bounded, recovery is observable, and an operator has a documented path.

Phase 12 adds prolonged outage, chaos, disruption, and cross-platform recovery testing to the feature-level suite already accumulated.
