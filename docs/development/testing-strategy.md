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

The Phase 4 Compose workflow proves customer-profile creation, address ownership,
single-default-address replacement, Cart item accumulation caps, optimistic Cart
version fencing, partial consumption, and durable Cart clearing through the
public edge. It uses unique customer and variant identifiers and makes no
assumption about existing platform data.

Chat covers two authenticated users, membership, database commit before ACK, realtime delivery, reconnect catch-up, deduplication, attachments, and later multi-pod fan-out. Customer support coverage also proves metadata-only queue visibility, atomic single-agent claim, loss of access after release, and denial of unclaimed agents. Edge coverage proves HTTPS routing, redirect, headers, basic rate limits, blocked internal paths, no direct API host port, and Chat WebSocket upgrades.

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

Phase 12 adds bounded dependency outage, disruption, and recovery testing to
the feature-level suite already accumulated. Its first implementation runs
only inside the isolated Compose integration topology, uses explicit service
allow-lists and `finally` recovery, and proves durable outbox/task-intent and
database fallback behavior. It also verifies that a Chat WebSocket can
authenticate after the Redis outage has recovered, so an interrupted Redis
subscription cannot leave the connection limiter permanently unavailable.
Kubernetes disruption is deferred until a reviewed cluster recovery controller
and target operational boundary exist.
