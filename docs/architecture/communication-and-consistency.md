# Communication and Consistency

## Transport responsibilities

| Mechanism | Question answered | Use | Do not use for |
|---|---|---|---|
| REST | What is the immediate result? | Synchronous commands and queries | Durable fan-out or long-running workflows |
| Kafka | What happened? | Durable domain facts, replay, projections, eventual consistency | Directed background task execution |
| RabbitMQ + Celery | What work must be executed? | Retryable background tasks and scheduled/maintenance work | Authoritative domain-event history |
| Redis Pub/Sub | What should connected clients see now? | Ephemeral realtime fan-out | Critical business events |
| WebSocket | What realtime client interaction is active? | Bidirectional Chat connections | Durable message storage |
| Object storage | Where do file bytes live? | Large binary data and generated artifacts | Relational business metadata |

`gRPC` is not part of the initial architecture. REST remains the synchronous baseline until measured requirements justify another protocol through an ADR.

## Local transaction boundaries

Every use case has one service-owned database transaction. Network calls do not occur while that transaction is open.

For an event-producing state change:

```text
BEGIN
  write business state
  write outbox event
COMMIT
```

An outbox publisher later publishes to Kafka and marks success after broker acknowledgement. If publication succeeds but marking fails, the event may be sent again. Consumer idempotency is mandatory.

## Event envelope

Every Kafka event uses the canonical schema under `contracts/events/`. The envelope carries identity, type/version, aggregate information, producer, UTC occurrence time, correlation, causation, trace context, and payload.

- `correlation_id` follows the logical workflow.
- `causation_id` identifies the immediate triggering request/event/task where available.
- W3C trace context should travel in transport headers; the envelope's trace field supports diagnostics and contract visibility.
- Consumers ignore unknown optional envelope fields and validate the selected event payload schema. Removing or changing an existing envelope field requires a new envelope version.

## Topic, key, and consumer-group rules

- Topics initially group events by bounded context under the `fastapi-platform` namespace.
- Event schema version is explicit in the event type, for example `order.created.v1`.
- A breaking event schema uses a new event version.
- Topic-version migration policy is separate and remains an explicit open decision.
- A message key preserves ordering only within one partition.
- Aggregate events normally use an aggregate ID; checkout integration events may require a workflow key such as `order_id`.
- Every consuming service uses its own consumer group. Replicas of the same service share that group where appropriate.

## Inbox and idempotency

The robust Kafka consumer transaction is:

```text
BEGIN
  insert unique inbox record for event + consumer
  apply conditional business transition
  write resulting outbox records
COMMIT
commit Kafka offset
```

Inbox deduplication by `event_id` prevents transport duplicates. Business uniqueness and state-machine guards prevent semantic duplicates that arrive under different event IDs.

## Dead letters

Kafka and RabbitMQ DLQs preserve:

- original payload/envelope;
- source topic/queue, partition, and offset where applicable;
- consumer/task identity;
- failure reason and exception category;
- retry history and timestamps;
- correlation, causation, and trace context.

DLQs require ownership, alerting, inspection, repair, and replay runbooks. Replay always passes through normal idempotency controls.

For Kafka, the acknowledgement sequence is mandatory:

```text
process one source record
  -> bounded retries with exponential backoff
  -> publish kafka.dead_letter.v1 after final failure
  -> Kafka acknowledges DLQ publication
  -> commit exactly that source topic/partition/offset
```

The consumer must not handle a later record from that partition, or commit the
source offset, while DLQ publication is unavailable. A duplicate DLQ record is
possible after an ambiguous broker acknowledgement and is deduplicated by the
immutable source topic, partition, and offset.

## RabbitMQ task delivery

Task queues are owned by bounded context and workload. Every task defines acknowledgement timing, retryable exceptions, exponential backoff, jitter, maximum attempts, time limits, idempotency, and poison-task behavior.

A Kafka consumer or database transaction cannot directly publish a task and assume atomicity. Before the first critical flow relies on RabbitMQ, its consuming phase must define a durable task-dispatch record/outbox or an equally explicit publisher-confirm and consumer-offset protocol.

## Chat consistency

Chat commits a Message to PostgreSQL before sender acknowledgement and Redis publication. It fans out locally before its cross-pod publication; an origin instance ignores its own Redis notification. Redis loss therefore degrades live delivery, not durability. Clients use stable IDs/cursors to retrieve missed messages and deduplicate frames after reconnect.

If requirements later demand guaranteed eventual fan-out after a commit-to-publish crash, Chat adds a durable relay. Redis Pub/Sub itself remains ephemeral.

WebSocket connection limiting is security-sensitive and therefore fail-closed when Redis is unavailable. Pub/Sub, presence, and an already authenticated Message send are not rate-limit truth and remain independent from Redis durability. Presence returns `unknown` during Redis failure rather than a false offline result. Chat-to-Media attachment URL authorization uses a short-lived service proof after Chat validates membership; Media validates only its own asset lifecycle and never reads Chat data.

## Failure model

- Kafka outage: committed state and outbox survive; publication retries.
- Duplicate event: Inbox and state guards eliminate repeated effect.
- RabbitMQ outage: durable task intent survives; dispatch retries.
- Worker crash: unacknowledged work is redelivered; task effect remains idempotent.
- Redis outage: cache/presence/fan-out degrade; durable state survives.
- Object-storage outage: lifecycle remains pending/failed; no false readiness.
- Pod termination: intake stops, work drains, unfinished broker work is redelivered.
