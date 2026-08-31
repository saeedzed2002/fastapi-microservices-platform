# ADR-035: Separate API and asynchronous runtime workloads

- Status: Accepted
- Date: 2026-08-31
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

The architecture requires stateless HTTP API Pods and separate consumer and
worker workloads. The previous Kubernetes foundation configuration enabled
Kafka outbox publishers, Kafka consumers, and RabbitMQ task dispatchers in
the FastAPI application lifespans. Every API replica therefore ran those
loops. API `HPA` scaling and rolling deployment could rebalance consumer
groups, multiply publisher polling, and restart dispatchers in response to
HTTP demand rather than asynchronous workload demand.

The repository already had separate Celery and payment-expiry Deployments, but
that did not isolate the remaining Kafka and durable dispatch loops. The
durable Outbox, Inbox, task-intent, leasing, and idempotency rules remain
correct; the runtime placement did not match the architecture or the API HPA
decision.

## Decision

Kubernetes foundation configuration disables all Kafka publisher, Kafka
consumer, invoice-consumer, and task-dispatcher flags by default. API Pods
therefore expose HTTP/WebSocket contracts only and do not start background
loops from their lifespans.

Each service that owns an asynchronous loop receives a dedicated, one-replica
event-worker Deployment using the same immutable service image and runtime
Secret. A small service-owned module starts only its configured loops and
handles termination by stopping the loops, disposing its own database engine,
and exiting for Kubernetes restart policy. The dedicated Deployments are:

- Identity outbox publisher;
- Customer, Search, Inventory, Order, Payment, and Notification Kafka
  consumers as applicable;
- Catalog, Inventory, Order, Payment, and Media outbox publishers as
  applicable; and
- Media, Order, and Notification durable task dispatchers.

The existing Order/Notification/Media Celery workers and Payment expiry worker
remain separate workloads. Raw Kustomize manifests and the Helm chart define
the same processes and explicit per-container environment overrides. API HPA
objects target only HTTP API Deployments; event workers remain at one replica
until a queue-depth scaling design is selected.

Local Docker Compose intentionally keeps the feature flags enabled in API
containers as a developer-convenience topology. It validates business flows,
but is not evidence that local API and asynchronous process placement matches
the Kubernetes delivery runtime.

## Consequences

### Positive

- HTTP demand, API `HPA`, and API rollout no longer directly own Kafka
  membership, outbox polling, or RabbitMQ task dispatch.
- Every long-running asynchronous process has an explicit Kubernetes identity,
  image, resource envelope, and termination behavior.
- A temporary worker outage delays durable work but does not lose committed
  Outbox or task-intent records; the existing leases and idempotency rules make
  recovery safe.

### Negative and risks

- Each dedicated event worker currently combines several loops from one bounded
  context. A crash restarts those loops together; independently scaling an
  individual loop requires later measured throughput and queue-depth evidence.
- The number of Pods and database/broker connections increases. Namespace
  resource quotas and environment capacity must include the extra workers.
- Local Compose still co-locates loops for simplicity, so contributors must use
  Kind conformance to verify the production-shaped process topology.

## Alternatives considered

- Leave asynchronous loops in API lifespans: rejected because it violates the
  stateless API model and makes CPU-based API HPA affect consumer ownership.
- Disable the API flags without replacement workers: rejected because Outbox
  publication, event processing, and task dispatch would stop.
- Run a FastAPI server in each worker Pod: rejected because it retains an
  unnecessary HTTP process and readiness model for a non-HTTP workload.
- Add `KEDA` now: deferred because the platform has no selected queue-depth
  metric, backlog target, or provider-rate-limit policy for worker scaling.

## Compatibility and migration

No public API, event schema, database schema, or service ownership contract
changes. A raw-manifest or Helm release must apply the disabled API defaults
and event-worker Deployments together. During the brief transition, durable
work can be delayed but remains recoverable from service-local Outbox and task
intent records; operators must not delete those records to accelerate a
rollout. Rollback restores the prior configuration only after the older API
image and its in-process loops are confirmed compatible.

## Validation

- Unit tests verify that the canonical error-free worker runner stops on
  termination and treats unexpected worker exit as a failed process.
- Static tests require every background flag to be disabled for API defaults,
  every dedicated event-worker command and override to be present in raw and
  Helm delivery, and Kind conformance to wait for those Deployments.
- Raw Kustomize and Helm renders validate the exact generated objects.
- The disposable Kind conformance run executes the in-cluster checkout, event,
  invoice, and notification workflow with API and asynchronous workloads
  separated.

## Related material

- [ADR-004](ADR-004-kafka-domain-events.md)
- [ADR-005](ADR-005-outbox-inbox-and-idempotency.md)
- [ADR-006](ADR-006-rabbitmq-celery-tasks.md)
- [ADR-010](ADR-010-kubernetes-first-runtime.md)
- [ADR-033](ADR-033-horizontal-pod-autoscaling.md)
- [Kubernetes deployment runbook](../runbooks/kubernetes-deployment.md)
