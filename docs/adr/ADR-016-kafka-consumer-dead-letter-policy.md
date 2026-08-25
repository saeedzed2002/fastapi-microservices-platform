# ADR-016 — Kafka Consumer Dead-Letter Policy

- Status: `Accepted`
- Date: `2026-08-26`
- Owners: `platform engineering`
- Supersedes: `none`
- Superseded by: `none`

## Context

Kafka consumers previously logged a processing exception and continued their
iteration. A later offset commit could therefore acknowledge a poisoned record
without a durable repair record. Conversely, a permanent failure that happened
to remain uncommitted could reappear after every restart with no bounded route
to inspection or recovery.

The platform already requires at-least-once delivery, durable inbox effects,
and inspectable dead letters. It needs one policy for all implemented Kafka
consumer groups without sharing domain models between services.

## Decision

Each Kafka consumer processes one record synchronously. It retries the record a
bounded number of times with exponential backoff. After the final failed
attempt, it publishes `kafka.dead_letter.v1` to
`fastapi-platform.dead-letter.v1`, keyed by the immutable source
`topic:partition:offset` coordinates.

The consumer commits exactly that source offset only after Kafka acknowledges
the DLQ publication. If DLQ publication is unavailable, it does not commit the
source record or process a later record. DLQ records preserve source bytes,
headers, source coordinates, consumer identity, retry history, and available
event correlation, causation, and trace context.

The shared `platform-messaging` library contains transport-only retry, exact
offset commit, and DLQ serialization code. It owns no business rules, event
payload models, database models, or service configuration.

## Consequences

### Positive

- Poison records become durable, searchable operational artifacts.
- A later success cannot silently commit past an earlier failed record.
- The normal source topic remains available for replay and business consumers.
- All current consumer groups follow one explicit acknowledgement boundary.

### Negative and risks

- A permanently unavailable DLQ blocks the affected partition deliberately.
- The DLQ write is at-least-once: a broker acknowledgement ambiguity can create
  duplicate DLQ records. Operators deduplicate by source coordinates.
- Retry counts are local to a running process. A crash before DLQ publication
  restarts the bounded attempt cycle; no source record is lost.
- DLQ payloads can contain original business data and require restricted access
  and retention controls.

## Alternatives considered

- Log and continue: rejected because it can commit past the failed record.
- Never commit failed records: rejected because a poison record blocks recovery
  indefinitely without a durable inspection path.
- Use a RabbitMQ queue as the Kafka DLQ: rejected because Kafka source
  coordinates, replay behavior, and durable event operations belong in Kafka.
- Add a durable per-attempt database ledger now: deferred. It is only necessary
  if operations require retry limits to survive a process crash before DLQ
  publication; it would add a database ownership decision per consumer.

## Compatibility and migration

`kafka.dead_letter.v1` is a new technical contract and does not alter any
existing domain-event schema. Consumers gain three configuration values with
safe defaults: the DLQ topic, maximum attempts, and retry backoff.

Deploy the producer-capable consumer images before disabling Kafka automatic
topic creation in an environment. Provision
`fastapi-platform.dead-letter.v1` with the required retention, ACL, alerting,
and replication policy before production rollout. Rollback is safe: no source
offset is committed unless either normal processing or the DLQ broker write has
succeeded.

## Validation

- Unit tests prove successful records commit their exact offset.
- Unit tests prove a poison record is retried, dead-lettered, then committed.
- Unit tests prove a DLQ broker failure leaves the source offset uncommitted.
- Contract validation checks the versioned DLQ envelope and immutable message
  key.
- Compose validation and integration tests build the services with the shared
  transport package.

## Related material

- Contracts: [`kafka.dead_letter.v1`](../../contracts/events/kafka.dead_letter.v1.schema.json)
- Diagrams: [`communication-and-consistency.md`](../architecture/communication-and-consistency.md)
- Runbooks: [`kafka-dlq.md`](../runbooks/kafka-dlq.md)
- Issues: none
