# Kafka Dead-Letter Runbook

## Detection

An alert reports records on `fastapi-platform.dead-letter.v1`, or service logs
contain `kafka_record_dead_lettered`. A sustained inability to write the DLQ
also blocks the affected source partition and increases consumer lag.

## Safe checks

1. Identify the DLQ record by its key:
   `source.topic:source.partition:source.offset`.
2. Inspect the preserved source bytes, headers, failure history, and event
   correlation fields. Treat payloads as restricted business data.
3. Check Kafka broker health, DLQ topic ACLs, retention, partition capacity,
   and the consumer group's lag for the source topic.
4. Determine whether the failure is malformed input, an incompatible event
   contract, a temporary dependency outage, or a service defect. Do not alter
   an owning service's database directly.

## Recovery

Repair the failing consumer code, dependency, or source data through the owning
service's approved procedure. A replay must publish the original source record
to its original topic with its normal aggregate key and must pass through the
normal Inbox and state-machine guards. Do not replay directly from the DLQ into
an arbitrary consumer group or manually commit source offsets.

If DLQ publication itself is unavailable, restore Kafka or the DLQ topic first.
The consumer intentionally leaves the source offset uncommitted and does not
process later records from that partition.

## Verification

Confirm the source group lag falls after recovery, the repaired record has one
idempotent business effect, and the DLQ record has a documented resolution.
Track duplicate DLQ records by source coordinates, not by Kafka DLQ offset.
