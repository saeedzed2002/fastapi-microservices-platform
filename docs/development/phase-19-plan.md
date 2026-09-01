# Phase 19 Plan — Post-delivery returns and refund lifecycle

## Outcome

Add a durable, full-order return workflow after delivery. Customers request a
return, administrators make the commercial decision and record physical
receipt, Inventory restores stock exactly once after receipt, and Payment
performs the existing provider-owned reversal with an auditable correlation.

## Scope

- an Order-owned ReturnRequest aggregate, decision/receipt audit, customer
  ownership checks, and idempotent customer and administrator commands;
- an additive return projection in customer and administrator Order responses;
- `order.return_received.v1`, whose no-PII SKU/quantity snapshot lets
  Inventory restore received stock through Inbox deduplication;
- additive return correlation on the established refund request and outcome
  facts so financial refund events cannot duplicate physical restocking;
- Order, Inventory, Payment, contracts, migrations, runbook, Compose and Kind
  evidence for the complete workflow.

## Non-goals

- partial-line returns, exchanges, replacement shipments, return labels,
  carrier webhooks, warehouse management, or customer return tracking;
- automatic Zibal refunds, settlement reporting, or fabricated provider
  reversal success;
- cross-service database access, distributed transactions, or a network call
  while holding an Order transaction open;
- restocking merchandise merely because a financial provider refund succeeds.

## Sequence

1. Completed: define the ownership decision and proposed canonical return API
   and receipt event contracts.
2. Add the Order return aggregate, migration, customer request, administrator
   decision/receipt commands, and customer/admin projections.
3. Add additive return correlation to the existing refund workflow and consume
   provider outcomes without regressing pre-delivery refund behavior.
4. Add the Inventory receipt consumer and one-return-one-restock movement
   guard.
5. Add contract, failure, Compose, and disposable-Kind E2E evidence for
   duplicate receipt, payment failure, and post-delivery stock safety.

## Acceptance evidence

- only the customer who owns a delivered order can create its one return
  request, and duplicate keys replay the same result;
- staff cannot mark a rejected or undelivered order as received;
- Inventory restores full-order stock only after one durable receipt fact;
- a correlated payment success never causes a second physical restock;
- payment failure preserves the received-return audit and restores the
  customer-visible pre-refund delivery state;
- all service boundaries, API/event contracts, migrations, and cross-service
  workflows have reviewable local, Compose, and Kind evidence.
