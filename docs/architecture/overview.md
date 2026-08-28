# Architecture Overview

## Purpose

FastAPI Microservices Platform is a backend-only distributed system. E-commerce provides concrete workflows for evaluating bounded contexts, local transactions, asynchronous consistency, concurrency, idempotency, failure recovery, observability, security, and independent delivery.

The platform is not a set of FastAPI processes sharing a database. Every service owns a business capability, durable state, migrations, contracts, tests, image, and operational behavior.

## System context

Clients communicate through the Nginx edge layer. Local Compose exposes the canonical `https://localhost:8443` API origin, performs TLS termination, basic limits, edge headers, and Chat WebSocket forwarding; API services are private to the Compose network. Domain authorization remains the responsibility of each service. Presigned S3 object bytes remain direct to compatible object storage because their signed canonical request must not be rewritten by an edge path prefix.

```text
Clients
   |
   v
Edge / API Gateway
   |
   +---------------- REST ----------------+
   |                                      |
   v                                      v
FastAPI API pods                    WebSocket Chat pods
   |                                      |
   | local ACID                           | persist first
   v                                      v
service-owned PostgreSQL            chat PostgreSQL
   |                                      |
   | outbox                               | publish second
   v                                      v
Kafka domain events                 Redis fan-out
   |
   +--> independent consumers
   |
   `--> task intent --> RabbitMQ --> Celery workers

File data plane: clients/workers <--> S3-compatible object storage
```

## Component responsibilities

### FastAPI services

- Expose versioned HTTP or WebSocket contracts.
- Enforce domain and resource-level authorization.
- Execute application use cases and local transactions.
- Produce and consume explicit integration contracts.
- Remain stateless at the process/pod level.

### PostgreSQL

- Stores durable business truth and audit-relevant history.
- Provides one local transaction boundary per service.
- Stores outbox, inbox, task-dispatch, or idempotency records where required.
- Never becomes a cross-service shared model.

Multiple service databases may run on one physical PostgreSQL instance locally. Separate ownership, credentials, grants, and migrations preserve the architectural boundary.

### Kafka

- Carries durable, replayable domain facts.
- Enables independent consumer groups and eventual consistency.
- Preserves ordering only within a partition; aggregate or workflow keys must be deliberate.
- Uses at-least-once delivery assumptions and idempotent consumers.

### RabbitMQ and Celery

- RabbitMQ brokers directed work.
- Celery executes background work in bounded-context-specific workers.
- Tasks have explicit retry, backoff, jitter, maximum-attempt, acknowledgement, idempotency, and DLQ behavior.
- Tasks do not replace domain events.

### Redis

- Accelerates caches and rate limiting.
- Holds short-lived OTP/session/revocation state where appropriate.
- Provides WebSocket fan-out, presence, and temporary counters.
- Is disposable and never the sole durable source of business truth.

### S3-compatible object storage

- Stores avatars, product media, chat attachments, generated invoices, and temporary uploads.
- Is accessed through an `ObjectStorage` port and `S3ObjectStorage` adapter.
- Uses MinIO initially without coupling application logic to MinIO-specific APIs.

### Platform and delivery

- Docker Compose provides local dependencies and the pinned Nginx edge gateway. Generate its ignored self-signed certificate before starting the local stack; see the edge gateway runbook.
- Kubernetes provides deployment, probes, scaling, disruption handling, policy, and controlled migrations in Phase 9.
- Helm packages stable Kubernetes resources in Phase 10.
- CI/CD grows from source validation to controlled immutable image delivery and verified rollout.
- OpenTelemetry, Prometheus, Grafana, Loki, and Tempo provide traces, metrics, logs, dashboards, and operational evidence.

## Consistency model

There is no distributed ACID transaction across services. Each service commits local business state and its outbox atomically. Kafka then propagates facts. Consumers update their own state and emit further facts using their own local transactions.

Cross-service workflows therefore use:

- eventual consistency;
- explicit state machines;
- choreography-based Saga reactions initially;
- compensating actions;
- at-least-once delivery;
- Inbox and business-key idempotency;
- reconciliation for stuck or late workflows.

## Primary checkout flow

```text
Order created + outbox
   -> order.created.v1
Inventory reservation
   -> inventory.reserved.v1 | inventory.reservation_failed.v1
Payment attempt
   -> payment.succeeded.v1 | payment.failed.v1
Order confirmation or cancellation
   -> invoice and notification work after confirmation
```

Inventory failure cancels the order before payment. Payment failure cancels the order and releases the reservation. Duplicate events must not repeat reservation, payment, release, confirmation, invoice, or notification effects.

## Realtime chat flow

```text
authenticated WebSocket message
   -> validate membership
   -> validate sender-owned ready Media attachments when present
   -> commit Message in Chat PostgreSQL
   -> acknowledge sender
   -> fan out to local participant connections
   -> publish notification through Redis for other Chat pods
```

Redis failure may interrupt cross-pod realtime delivery but cannot lose committed chat messages. Clients recover from durable history using stable cursors or message IDs. Redis-backed connection limiting is fail-closed; Pub/Sub and presence are not. A Chat-authorized participant receives a Media-generated short-lived attachment URL only after Chat membership validation and Media verification of a short-lived service proof.

## Runtime model

API pods are stateless and normally run one application process per pod. Workers and consumers are separate workloads. Durable files are never written to container-local paths. Configuration is environment-based, secrets are externalized, and all workloads require appropriate startup, liveness, readiness, shutdown, and resource behavior.

## Evolution rule

Architecture is implemented phase by phase. Each phase designs, implements, tests, documents, validates, and reviews its scope before the next phase begins. Major changes require an ADR; minor reversible implementation decisions may proceed within accepted boundaries.
