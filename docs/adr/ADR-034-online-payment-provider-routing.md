# ADR-034: Online payment provider routing and safe fallback

- Status: Accepted
- Date: 2026-08-31
- Owners: platform engineering
- Supersedes: the single-provider routing assumption in ADR-022 and ADR-023 only
- Superseded by: none

## Context

The platform previously exposed only the explicit `zarinpal` payment method.
That proves one real provider adapter, but it gives a customer no alternative
when Zarinpal definitively rejects a new payment request. A second provider
must not be bolted into Order, Cart, or a frontend client: Payment owns
provider credentials, attempts, browser-return tokens, expiry, verification,
and the durable payment facts consumed by the checkout Saga.

Provider request timeouts are financially ambiguous. A request may have
created a payable transaction even when Payment did not receive a response.
Automatically issuing the same amount to a second provider after that outcome
can create two customer charges. Provider health checks do not prove that an
individual request was not accepted, so they cannot make that retry safe.

## Decision

Add the additive `online` payment method. `Order` can create an `online` order
through `POST /api/v1/orders/cart/online`; it makes the same bounded Saga
observation as the existing explicit Zarinpal path and then calls
`POST /api/v1/payments/orders/{order_id}/online`. Payment keeps the existing
explicit Zarinpal APIs intact for direct-provider recovery and compatibility.

Payment prefers Zarinpal when it is configured. It creates and commits a
Payment-owned `REQUESTING` attempt before each provider call. If Zarinpal
returns a definitive rejection, Payment records that `REJECTED` attempt and,
only when Zibal is configured, creates a new Zibal attempt. A successful
Zibal request persists its opaque `trackId` in the existing Payment authority
column and returns the Zibal start URL. If Zarinpal is locally unconfigured,
Payment may start with configured Zibal because no external request has been
made.

Payment does not fall back after a Zarinpal network error, timeout, invalid
response, or server failure. The original attempt stays `REQUESTING` and
requires operator reconciliation. The same rule applies to a Zibal request.
One intent may therefore have a durable rejected Zarinpal attempt followed by
a Zibal attempt, but it never has two attempts whose external outcome is
unknown.

`GET /api/v1/payments/zibal/callback?trackId=...` is public only as a browser
return. It finds a Payment-owned Zibal attempt and always calls Zibal verify;
the query parameter is not payment proof. A successful verify emits the
unchanged `payment.succeeded.v1` fact once. Expiry and late-success handling
remain the ADR-022 policy and now include `online` intents.

The adapter uses the already locked `HTTPX` runtime dependency. Zibal's
published SDK demonstrates the `merchant`, `callbackUrl`, `amount`,
`trackId`, `request`, `start`, and `verify` protocol; no third-party Python
SDK is introduced. Both routed providers are restricted to positive whole
`IRT` amounts.

Zarinpal short-window reversal remains available when an `online` intent
actually succeeded through Zarinpal. A Zibal success is intentionally not
represented as a fabricated local refund: its full or partial refund and
settlement workflow requires a separately approved provider-specific design.
An administrator request for that payment follows the existing durable refund
failure path and returns the Order to `CONFIRMED`.

## Consequences

### Positive

- Customers have a real provider alternative without leaking credentials or
  routing policy outside Payment.
- Every provider attempt remains attributable, durable, and independently
  reconcilable by provider and opaque token.
- The original checkout Saga facts, Order ownership checks, and Cart cleanup
  behavior remain unchanged.
- Explicit Zarinpal clients continue to use their reviewed API without a
  breaking contract change.

### Negative and risks

- A provider outage after a request begins still requires reconciliation; this
  is an intentional availability trade-off for payment safety.
- Zibal credentials and a registered public callback URL are operational
  prerequisites. Empty credentials leave the provider disabled rather than
  using a fake fallback.
- Zibal refunds are not implemented. Calling the existing administrator
  refund command for an `online` payment settled by Zibal produces the
  existing durable refund-failed result; it must be handled through the
  provider settlement workflow until a dedicated design exists.

## Alternatives considered

- Retrying the same transaction against Zibal after any Zarinpal error was
  rejected because a timeout cannot distinguish failure from a created charge.
- Letting Order select a provider was rejected because it would duplicate
  provider policy in a context that does not own payment attempts or browser
  verification.
- Replacing the explicit Zarinpal API was rejected because it is a valid,
  versioned recovery path and existing callers must remain compatible.
- Adding a generic payment SDK dependency was rejected because the reviewed
  `HTTPX` adapter is smaller, locked, and exposes the exact protocol boundary.

## Compatibility and migration

No database migration is required: the existing opaque Payment attempt
authority stores either a Zarinpal authority or a Zibal `trackId`, while the
existing provider field preserves their meaning. Existing `zarinpal`,
`test_success`, and `test_failure` methods and all event payloads are
unchanged. `online` and its Cart/Payment endpoints are additive public API
contracts.

Configure `PAYMENT_ZIBAL_MERCHANT_ID`, `PAYMENT_ZIBAL_CALLBACK_URL`, and
`PAYMENT_ZIBAL_REQUEST_TIMEOUT_SECONDS` alongside the existing Zarinpal
settings. The routed providers must use the same currency. Production secrets
belong in the approved secret manager; `.env.example` and Kubernetes manifests
contain placeholders only.

## Validation

- Adapter tests validate Zibal request and verify paths, payloads, redirect
  construction, rejection, missing configuration, and transport failure.
- Workflow tests prove a definitive Zarinpal rejection creates a Zibal attempt
  and prove a Zarinpal network failure makes no Zibal call.
- OpenAPI, service-route, checkout validation, static, type, migration-head,
  contract-catalog, Compose, Kustomize, Helm, and repository CI checks remain
  required.
- A real Zibal sandbox or merchant transaction is separate observable runtime
  evidence because it depends on provider credentials, callback reachability,
  and provider availability.

## Related material

- Contracts: `contracts/openapi/payment-online.v1.openapi.json` and
  `contracts/openapi/order-checkout.v1.openapi.json`
- Runbooks: `docs/runbooks/online-payment-provider-routing.md`
- Issues: none
