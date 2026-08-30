# ADR-024: Two-role model and paid-order administration

- Status: Accepted
- Date: 2026-08-30
- Owners: platform engineering
- Supersedes: the role-management portions of ADR-019 and ADR-021; the manual-refund portion of ADR-022
- Superseded by: none

## Context

The initial platform accumulated `support_agent`, `catalog_admin`, and
`inventory_admin` roles before it had a product requirement for delegated
staff. It also confirmed provider payments without turning an Inventory
reservation into a committed stock decrement. Order administration was
read-only, so a confirmed Zarinpal order could neither advance through
fulfillment nor initiate a controlled reversal.

Those are operational defects, not deferred polish: confirmed orders must
settle stock, payment reversals must not race shipping, and an initial product
must not expose dormant privileged roles without a lifecycle need.

## Decision

Identity exposes exactly two active role values: `customer` and `admin`.
Customers use OTP; administrators use the existing interactive bootstrap
provisioning path and password login. There is no public role-assignment API
in this release. The legacy delegated-staff lifecycle API is removed. The
data migration keeps administrator and customer identities, promotes legacy
support-only accounts to `admin`, and suspends unknown retired-role sets.
Catalog, Inventory, Chat support queue, and Order administration accept only
`admin` for privileged work.

After `payment.succeeded.v1`, Inventory atomically changes each reservation
from `RESERVED` to `COMMITTED`, decrements both `on_hand` and `reserved`, and
writes an immutable `commit` movement. After `payment.refunded.v1`, it restores
committed stock with a `refund_return` movement. A reconciliation endpoint is
provided only for existing historical `RESERVED` records whose Order state is
already `CONFIRMED`; it calls Order's authenticated administrator API outside
an Inventory database transaction.

Order adds administrator fulfillment transitions:
`CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED`, with a carrier and tracking
number required for shipping. Each change writes an Order transition and an
Outbox fact in one local transaction.

An administrator creates a Zarinpal refund through
`POST /api/v1/orders/admin/{order_id}/refund` with an `Idempotency-Key`.
Order accepts only a confirmed Zarinpal order, transitions it to
`REFUND_PENDING`, records the request, and emits `order.refund_requested.v1`.
Payment consumes that durable request, persists its reversal record before the
provider call, and uses Zarinpal's documented short-window `reverse` endpoint.
Provider success emits `payment.refunded.v1`; rejection emits
`payment.refund_failed.v1`. Order then reaches `REFUNDED` or returns to
`CONFIRMED`. The intermediate state prevents shipping a payment while its
reversal is in progress.

This release intentionally implements only the provider's short reversal
window. Full or partial refunds require a separate approved workflow because
Zarinpal's refund API uses a different GraphQL access-token/session lifecycle
and requires independent settlement reconciliation.

## Consequences

### Positive

- Privileged behavior has one administrator role and no orphan lifecycle API.
- Confirmed sales reduce available stock exactly once, and reversals restore it
  exactly once.
- Refund and fulfillment cannot interleave into a shipped-but-refunded order.
- Every state change has a service-local audit path and durable outbox fact.

### Negative and risks

- One administrator role combines catalog, inventory, support-queue, and order
  operations. That is deliberate for the initial product; delegated roles need
  a later approved lifecycle and audit design.
- A timeout after a Zarinpal reverse request leaves Payment's reversal in
  `REQUESTING`. It must be reconciled from the persisted provider authority;
  automatic retries could duplicate an uncertain financial operation.
- A Zarinpal reversal is time-limited. Orders outside that window need the
  future full/partial refund capability, not a fabricated local success.

## Alternatives considered

- A general public role-assignment API was rejected because the initial product
  has no delegated-staff lifecycle, approval flow, or role-audit requirement.
  Adding one now would expose authority the product does not need.
- A direct Payment reversal endpoint was rejected because it could race an
  Order fulfillment update. The durable Order command establishes
  `REFUND_PENDING` before Payment contacts the provider.
- Treating Zarinpal reversal as a full refund was rejected because the provider
  documents a separate access-token/session-based refund API for full and
  partial settlement.

## Compatibility and migration

Identity migration `0006_two_role_model` retires legacy roles without deleting
historical audit rows. Inventory migration `0005_reservation_settlement` adds
committed/returned reservation timestamps. Order migration
`0006_order_fulfillment` adds fulfillment and refund-request records. Payment
migration `0004_payment_reversals` adds durable provider reversal state.

The new domain events are `order.refund_requested.v1`,
`payment.refunded.v1`, `payment.refund_failed.v1`, and
`order.fulfillment_updated.v1`. `payment.succeeded.v1` now has Inventory as a
consumer; its payload remains unchanged.

## Validation

- Unit tests cover stock commit/return idempotence, refund state transitions,
  administrator role gates, and Zarinpal reverse request/rejection behavior.
- Contract validation covers the new event schemas and Order administration
  API document.
- Migration-head checks cover Identity, Inventory, Order, and Payment.
- A sandbox reversal remains a separately observable runtime operation because
  it depends on the provider's window, merchant configuration, and network.

## Related material

- Contracts: `contracts/openapi/order-query.v1.openapi.json`,
  `contracts/openapi/payment-zarinpal.v1.openapi.json`, and
  `contracts/events/`
- Runbooks: `docs/runbooks/zarinpal-payment.md` and
  `docs/runbooks/admin-operations.md`
- Issues: none
