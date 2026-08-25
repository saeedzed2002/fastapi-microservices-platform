# Open Architectural Questions

The baseline architecture is accepted. The following contract and operational decisions remain deliberately open; implementation must not silently invent them.

## Decision required at Phase 1 entry

### Python and `uv` workspace topology

Decide whether one root `uv` workspace lock resolves all services or services maintain controlled independent lockfiles. Finalize this during Phase 1 planning and before creating any `pyproject.toml` or `uv.lock`. The decision must preserve reproducible builds, clear service image contents, affected-service CI, and independent service versioning.

## Decisions required before their first consumer phase

### Event schema representation and compatibility tooling

The canonical envelope uses JSON Schema in Phase 0. Before the first business event payload is proposed, decide whether JSON Schema remains the payload standard and how CI detects backward-incompatible changes. Do not add a schema registry unless an operational requirement justifies it.

### Kafka-to-RabbitMQ durable handoff

Resolved by ADR-015 for Invoice and Notification: each service records a local
task intent, dispatches through a claimed state and RabbitMQ publisher confirm,
and treats uncertain publication as safe duplicate task execution.

### Identity and service trust

Define JWT issuer/audience, signing algorithm, key distribution and rotation, downstream validation, service identity, and service-to-service authorization before Phase 2 Identity and Customer implementation.

### Media event consumers

Before Phase 3 activates `media.ready.v1`, define which bounded contexts consume it, whether they need a projection or synchronous readiness query, and how ownership/deletion races are handled.

### Redis degradation policy

Specify fail-open, fail-closed, or durable fallback behavior before each feature first depends on Redis: security state in Phase 2, Cart cache in Phase 4, and Chat fan-out/presence in Phase 7.

## Owner decision not blocking technical Phase 1 work

### License

The repository license is a legal/product decision. No license file is created until the owner selects one.

## Decisions required before Phase 5

### Authoritative checkout composition

Resolved by ADR-014: Order uses bounded REST snapshot queries before its local
transaction. Phase 5 does not accept discount, tax, or shipping-price claims
and snapshots only the authoritative Catalog amount and caller-owned Customer
address.

### Saga timeout and late-event policy

Resolved by ADR-014: late terminal payment facts never resurrect an Order.
Pending expiry remains visible to reconciliation; a real-provider refund
workflow is deferred.

### Order-state transition triggers

Resolved by ADR-014: Payment emits payment.processing.v1, which durably moves
an Order from INVENTORY_RESERVED to PAYMENT_PENDING.

### Checkout Kafka partition key

Resolved by ADR-014: all Phase 5 workflow events use order_id as their Kafka
key and correlation ID while consumers retain Inbox and state guards.

### Payment-provider interaction model

Resolved for Phase 5 by ADR-014: the deterministic fake provider owns an
intent, attempt, provider reference, and idempotency boundary. Webhooks and
real-provider unknown outcomes remain explicitly deferred.

## Additional decisions required before dependent features

### Chat realtime delivery guarantee

Confirm whether durable history plus reconnect catch-up is sufficient for the initial release. If eventual live fan-out must survive a commit-to-Redis-publish crash, introduce a durable relay without treating Redis as durable.

### Media and generated invoice ownership

Resolved for generation by ADR-015: Order owns Invoice metadata and bytes under
its own S3-compatible bucket. Retention, deletion, and customer download policy
remain open.

### Customer and Notification preferences

Phase 6 carries a checkout-time email contact snapshot only. User-controlled
preferences and unsubscribe policy remain open before additional channels ship.

### Order and Shipping status

Shipping should own carrier/fulfilment truth; Order should maintain only a customer-facing projection. Shipping currently has no Phase 0–12 implementation milestone and remains post-roadmap unless explicitly scheduled.

### Topic and event version migration

Event schema version is authoritative in event names. Define when a topic suffix changes, how old/new versions coexist, and whether dual publishing or parallel consumption is required.

### Observability operations

Before production-style deployment, define collector topology, propagation carriers, sampling, retention, cardinality limits, SLOs, alert ownership, and handling of exporter failure.

### Delivery and migration rollback

Define environment promotion, immutable digest handling, migration failure behavior, smoke-test gates, and rollback rules. Database rollback is not assumed to be equivalent to image rollback.
