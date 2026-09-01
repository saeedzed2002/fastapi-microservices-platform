# Phase 18 Plan — Shipping ownership extraction

## Outcome

Extract carrier references, tracking numbers, and shipment lifecycle from the
temporary Order-owned fulfillment implementation into `shipping-service`
without allowing a shipment update to race a payment reversal. Order retains a
customer-facing read projection and the financial eligibility fence; Shipping
becomes the authoritative shipment bounded context.

## Scope

- a new independently deployable `shipping-service` with its own PostgreSQL
  database, migration history, image, health endpoints, configuration, tests,
  and Kubernetes/Helm/Compose definitions;
- a durable Shipment aggregate keyed by `order_id`, created idempotently from
  the existing additive `order.confirmed.v1` fact;
- Shipping-owned administrator commands for `PROCESSING`, `SHIPPED`, and
  `DELIVERED`, with carrier and tracking number required before `SHIPPED`;
- a short-lived, Order-owned fulfillment-transition authorization that fences
  refund initiation while Shipping commits an approved status change;
- `shipping.status_updated.v1` as a minimal no-PII fact that Order consumes to
  update its existing customer-facing fulfillment projection;
- a compatibility facade for the established Order fulfillment endpoint during
  migration, with explicit timeout and idempotency behavior;
- contracts, ADR, runbook, migration evidence, and Compose/Kind E2E coverage.

## Non-goals

- carrier label purchase, carrier webhooks, rate shopping, delivery-estimate
  promises, address validation, return logistics, or a fabricated external
  carrier integration;
- copying the customer delivery address into Kafka or a Shipping database in
  this increment;
- a distributed transaction, cross-service database access, or automatic
  retry after an uncertain external command outcome;
- removing the existing `v1` Order fulfillment endpoint before its compatible
  Shipping facade and read projection are proven.

## Sequence

1. Completed: add the Shipping service skeleton, migration, `Shipment` lifecycle, and
   idempotent consumer of `order.confirmed.v1`.
2. Completed: add the Order-owned fulfillment-transition authorization record and its
   bounded expiry/recovery path. Refund initiation must return a conflict while
   such an authorization is active.
3. Completed in source: add authenticated Shipping status commands. Shipping
   obtains an Order authorization before its local commit, then writes
   `shipping.status_updated.v1` in its own outbox transaction. It rejects a
   commit after authorization expiry.
4. Completed in source: add the Order consumer and make `OrderFulfillment` a
   projection. The existing endpoint is a forwarding facade with explicit
   `Idempotency-Key`; it is not deprecated until topology migration evidence
   proves it is safe. An expired authorization is released only after a
   definitive Shipping recovery query; an unavailable result fails closed.
5. Completed: add Compose, Kind, contract, and failure tests for duplicate
   facts, concurrent refund/shipping commands, expired authorizations, and
   delayed projection delivery.

## Acceptance evidence

- Shipping owns exactly one durable shipment per confirmed order and no
  service reads another service's database;
- an administrator cannot ship or deliver a refunded/refund-pending order;
- a refund cannot begin while a valid fulfillment authorization is outstanding;
- duplicate Order or Shipping events do not create duplicate shipments or
  state transitions;
- customer Order queries show the Shipping-projected state without a
  synchronous customer query to Shipping;
- every new API and event has a canonical contract, and the controlled
  migration passes local, Compose, and disposable-`Kind` validation.
