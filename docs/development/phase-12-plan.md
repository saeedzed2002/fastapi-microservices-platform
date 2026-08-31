# Phase 12 Plan — Resilience and Recovery Evidence

## Outcome

Prove that selected durable workflows recover after a bounded local dependency
outage without losing committed business state or duplicating a completed
effect. The evidence is an opt-in Compose E2E suite; it is not a production
chaos platform or a target-environment availability claim.

## Scope

- controlled `docker compose stop`/`start` disruption of local `kafka`,
  `rabbitmq`, and `redis` services only;
- durable Catalog outbox recovery through Search after a Kafka outage;
- durable Order task-intent recovery through invoice generation and email
  delivery after a RabbitMQ outage;
- Cart PostgreSQL fallback while Redis is unavailable;
- bounded polling, unique test data, always-run service recovery, and an
  operator runbook;
- integration-CI execution in the existing Compose job.

## Non-goals

- deleting Kubernetes Pods, broker data, volumes, or namespaces;
- an unbounded outage, load test, public-environment test, or production SLO
  claim;
- changing database schemas, event contracts, business retries, or ownership
  boundaries solely to make a test pass;
- claiming that the disposable Kind workflow proves infrastructure disruption
  recovery without a reviewed cluster recovery controller.

## Failure matrix

| Dependency or workload | Trigger | Required durable invariant | Recovery proof |
|---|---|---|---|
| Kafka | stop before Catalog product publish | the published product and local outbox commit survive | Search receives one projection after Kafka restarts |
| RabbitMQ | stop before the Order invoice task dispatch | the Order task intent remains pending and records a failed dispatch attempt | restart causes one invoice object and one notification delivery |
| Redis | stop while Cart reads and writes | PostgreSQL Cart state remains authoritative | Cart write/read succeeds before and after Redis restarts |
The RabbitMQ scenario proves recovery across the existing worker and durable
queue path after the broker returns. A worker-only interruption is outside this
initial, dependency-focused suite and requires its own bounded failure matrix
before it can be added to CI.

## Safety controls

- The harness accepts only the allow-listed Compose service names and invokes
  `start` in a `finally` block for every stopped service.
- It never calls `down`, `rm`, `kill`, volume deletion, shell construction, or
  arbitrary container commands.
- Each test fails if the expected durable state is absent before recovery;
  merely observing eventual success after a restart is insufficient evidence.
- The suite is opt-in through `RUN_E2E=1` and runs in the existing isolated
  integration Compose topology.

## Acceptance evidence

- Kafka recovery proves a transaction committed during an outage appears in
  Search after the broker returns.
- RabbitMQ recovery observes a persisted failed task-dispatch attempt before
  restart, then proves invoice bytes and exactly one new Mailpit message.
- Redis recovery proves Cart reads and writes fall back to PostgreSQL.
- Every disruption is followed by an explicit health wait and service restart,
  even when the assertion fails.
- CI preserves Compose diagnostics on failure and local operators can follow
  the resilience-recovery runbook.
