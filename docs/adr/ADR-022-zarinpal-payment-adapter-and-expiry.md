# ADR-022: Zarinpal payment adapter and expiry

- Status: Accepted
- Date: 2026-08-29
- Owners: platform engineering
- Supersedes: none
- Superseded by: ADR-024 for the refund policy only; ADR-034 for routed online-provider selection only

## Context

ADR-014 deliberately used deterministic `test_success` and `test_failure`
methods. That was sufficient to prove the checkout choreography, but cannot
take a customer to a real payment page or prove that the provider accepted a
payment. The platform now requires a sandbox-capable Zarinpal flow without
giving Payment access to the Order database or keeping a database transaction
open during a provider request.

An order can be cancelled while an external payment page is open. A provider
response may also be unknown after a network failure. Those facts require a
durable Payment-owned intent, a bounded customer-payment window, and an
explicit late-success policy.

## Decision

Payment owns the Zarinpal adapter, payment-attempt state, authority, provider
reference, expiry, and provider verification. The existing `test_success` and
`test_failure` methods remain only as deterministic test contracts.

After `inventory.reserved.v1`, Payment creates a local `zarinpal` intent in
`AWAITING_CUSTOMER`, persists `payment.processing.v1` in the same transaction,
and gives the customer `PAYMENT_RESERVATION_MINUTES` to begin payment. A
customer begins payment through `POST /api/v1/payments/orders/{order_id}/zarinpal`.
Payment validates the caller locally and makes a bounded authenticated `REST`
request to Order's caller-owned order endpoint. Order remains the owner of the
ownership check and must report `PAYMENT_PENDING`; Payment never queries an
Order table.

Before calling Zarinpal, Payment commits a `REQUESTING` attempt. It then calls
the documented Zarinpal `v4` request endpoint outside every database
transaction. A returned authority is committed with `PENDING_CUSTOMER`; a
repeated start returns that same authority and redirect URL. A known provider
rejection returns the intent to `AWAITING_CUSTOMER`. An unavailable provider
leaves the durable `REQUESTING` state so an unsafe duplicate request is not
created automatically.

The browser return endpoint is intentionally public because it is a browser
redirect, not an authenticated server webhook. It accepts only a locally
persisted authority, never trusts `Status` as payment proof, and always calls
the Zarinpal `v4` verification endpoint before emitting success. Provider
verification and local authority lookup are the authentication boundary for
that callback. Callback cancellation and verification rejection reopen the
intent while it remains unexpired.

The owner-local expiry worker locks due Payment rows with `FOR UPDATE SKIP
LOCKED`. It marks the intent expired and writes `payment.failed.v1` to the
Payment outbox in the same transaction. The existing Order and Inventory Saga
consumers cancel the order and release stock. A verified success received after
expiry is recorded as `LATE_SUCCESS`, emits no success event, and requires
manual refund/reconciliation.

No event payload changes are needed: existing `payment.processing.v1`,
`payment.succeeded.v1`, and `payment.failed.v1` schemas continue to describe
the durable Saga facts. The new public Payment API is a separate versioned
contract.

The adapter uses the already locked `HTTPX` `0.28.1` runtime dependency rather
than an unreviewed third-party Python provider SDK. The Payment image pins the
same exact release. Timeouts are mandatory; provider payloads, credentials,
and browser tokens are not logged.

## Consequences

### Positive

- A customer can be redirected to the Zarinpal sandbox without exposing a
  provider credential to a client or another bounded context.
- Payment completion remains an outbox-backed durable fact and retains the
  existing Saga compensation behavior.
- Callback replay is idempotent after local success and cannot promote an
  unknown authority to a payment.
- Multiple Payment replicas can run the expiry loop safely.

### Negative and risks

- `REQUESTING` is deliberately a manual reconciliation state after an unknown
  request outcome; automatically retrying can create a second provider charge.
- A browser return URL must be reachable by the customer. `localhost` is only
  suitable for same-machine development and the self-signed local edge
  certificate must be trusted by that browser.
- A cancellation race remains possible across the Order and Payment service
  boundary; there is no distributed transaction with a provider. The expiry
  and late-success policy makes that case visible and prevents an order from
  being resurrected.
- Refund policy is superseded by ADR-024. The platform now supports only the
  documented short-window reversal; a late, full, or partial refund still
  requires a separate approved settlement workflow.

## Alternatives considered

- Keeping the fake provider was rejected because it cannot validate provider
  request, redirect, callback, or verification behavior.
- Calling Zarinpal inside an open database transaction was rejected because a
  remote timeout would hold local locks and couple database availability to a
  provider.
- Treating the browser `Status=OK` value as success was rejected because it can
  be forged or stale.
- Adding an unreviewed Zarinpal Python SDK was rejected. A narrow `HTTPX`
  adapter is easier to audit, already dependency-locked, and follows the
  published `v4` request and verification contract.

## Compatibility and migration

Payment migration `0003_zarinpal_payment_workflow` adds nullable expiry and
provider metadata. Existing historical attempts are backfilled as `fake` and
the old test methods remain valid. New checkout requests may use `zarinpal`
only with a positive whole `IRT` amount.

Local configuration is `ZARINPAL_MERCHANT_ID`, `ZARINPAL_SANDBOX`,
`ZARINPAL_CALLBACK_URL`, `ZARINPAL_REQUEST_TIMEOUT_SECONDS`, and
`PAYMENT_RESERVATION_MINUTES`. The default local callback is
`https://localhost/api/v1/payments/zarinpal/callback`, through the edge. The
old `ORDER_PAYMENT_RESERVATION_MINUTES` setting is not used: Payment owns the
payment deadline. No `FRONTEND_URL` is introduced because this repository is
backend-only. Production must register a public `HTTPS` callback URL in the
provider panel and inject the merchant ID from a secret store.

## Validation

- Adapter tests assert Zarinpal sandbox `v4` request/verify paths, request
  payload, redirect construction, rejection handling, and missing
  configuration behavior.
- Wiring tests assert edge-only Payment exposure, Order `REST` lookup, the
  expiry worker, and the callback configuration.
- Migration-head, contract-catalog, format, lint, type, unit, integration, and
  Compose configuration checks run in the repository validation workflow.
- The runbook defines recovery for `REQUESTING`, `VERIFYING`, expiry, and late
  success. A real sandbox transaction remains a separately observable runtime
  validation because it depends on provider availability and merchant state.

## Related material

- Contracts: `contracts/openapi/payment-zarinpal.v1.openapi.json`
- Diagrams: `docs/diagrams/checkout-saga.md`
- Runbooks: `docs/runbooks/zarinpal-payment.md`
- Issues: none
