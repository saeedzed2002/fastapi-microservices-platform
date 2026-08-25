# Event Contracts

`event-envelope.v1.schema.json` defines the required wrapper for all Kafka domain events.

## Envelope invariants

- `event_id` is the stable logical event ID and does not change during retry or republishing.
- `event_type` ends in `.vN`; `event_version` must equal `N` even though that cross-field rule requires application/CI validation beyond JSON Schema.
- `occurred_at` records the domain occurrence time in UTC, not publication or consumption time.
- `correlation_id` follows the complete business workflow.
- `causation_id` identifies the immediate causal request/event/task when one exists.
- `trace_id` supports diagnostics. Full OpenTelemetry continuation uses standard message headers such as `traceparent` and optionally `tracestate`.
- `payload` is validated by the schema for the selected `event_type`.
- Broker metadata such as partition, offset, retry count, and publication timestamp is not part of the domain envelope.
- Consumers ignore unknown optional envelope fields. Existing fields cannot be removed, renamed, or assigned incompatible semantics without a new envelope version.
- Platform-generated request, correlation, and causation identifiers should use UUIDs by default, but contracts accept bounded transport-safe identifiers from trusted upstream systems.

## Delivery assumptions

- Critical producers write business state and an outbox record atomically.
- Kafka delivery is treated as at least once.
- Consumers atomically record Inbox processing with their business effect.
- Consumers additionally enforce business-key uniqueness and legal state transitions.
- A message key provides partition-local ordering only.

## Schema files

The active identity.user_registered.v1 payload is owned by identity-service and
consumed by customer-service. Its producer publishes the full envelope and its
payload is validated against the catalog-linked schema. Reserved names in
contracts/catalog.json are not permission to publish an unspecified payload.

media.ready.v1 is owned by media-service. It is active in Phase 3 and has no
consumer group yet; it remains durable and replayable for later approved
consumers. Its payload is defined in media.ready.v1.schema.json.
