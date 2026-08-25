# Payment Service

Payment owns payment intents, attempts, and its Inbox and Outbox records. It
does not own orders, inventory reservations, or customer payment credentials.

For Phase 5 it consumes `inventory.reserved.v1` and uses `test_success` and
`test_failure` as a deterministic fake-provider contract. The local transaction
persists one intent, one attempt, `payment.processing.v1`, and a terminal
payment fact. A unique order identifier and Inbox event identifier make replay
and duplicate delivery safe.

No real provider, payment token, webhook, refund, or PCI-sensitive data exists
in this phase.
