# Payment Service

Payment owns payment intents, attempts, provider authorities, expiry, and its
Inbox and Outbox records. It does not own orders, inventory reservations, or
customer payment credentials.

It consumes `inventory.reserved.v1`. The deterministic `test_success` and
`test_failure` methods remain available for automated checkout coverage.

## Provider-routed online workflow

The additive `online` method starts at
`POST /api/v1/payments/orders/{order_id}/online`. Payment prefers configured
Zarinpal and can use Zibal only after a definitive Zarinpal rejection. A
timeout, network failure, malformed provider response, or provider `5xx`
leaves the first attempt in `REQUESTING`; it never creates a second payable
request. `GET /api/v1/payments/zibal/callback?trackId=...` always verifies the
persisted track ID before emitting a success fact.

Configure `ZIBAL_MERCHANT_ID` and its registered edge callback URL in addition
to the Zarinpal values. Both routed providers require whole `IRT` amounts. A
routed Zarinpal success remains eligible for the documented short reversal;
Zibal refunds require a separate settlement design and are not fabricated.

## Zarinpal sandbox workflow

The `zarinpal` payment method creates a Payment-owned intent after inventory
reservation. A customer starts payment through
`POST /api/v1/payments/orders/{order_id}/zarinpal`; Payment asks Order to
enforce caller ownership and `PAYMENT_PENDING` state over authenticated REST.
It then creates a Zarinpal authority outside any database transaction.

The public browser-return endpoint
`GET /api/v1/payments/zarinpal/callback` accepts only a persisted authority and
always verifies an `OK` return with Zarinpal before writing
`payment.succeeded.v1` to the local outbox. A non-`OK` return reopens only a
`PENDING_CUSTOMER` attempt. It cannot cancel an attempt in `VERIFYING`.

Payment expires incomplete intents with a replica-safe worker and emits
`payment.failed.v1` in the same transaction. A verified success after expiry
is recorded as `LATE_SUCCESS` and requires manual refund/reconciliation.

An administrator starts a refund through Order's durable
`POST /api/v1/orders/admin/{order_id}/refund` command. Payment consumes
`order.refund_requested.v1`, persists a reversal record, then calls Zarinpal's
short-window reverse endpoint outside a database transaction. It emits either
`payment.refunded.v1` or `payment.refund_failed.v1`. Full or partial refunds
are deliberately not implemented because they require Zarinpal's separate
GraphQL access-token/session workflow and settlement reconciliation.

Configure `ZARINPAL_MERCHANT_ID`, `ZARINPAL_SANDBOX`, and the edge callback URL
through the ignored `.env` file. Payment validates the merchant identifier
before persisting a payment request, so a missing local configuration cannot
leave an order in `REQUESTING`. Apply Payment migrations from the workspace:

    pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-payment

See `docs/adr/ADR-022-zarinpal-payment-adapter-and-expiry.md` for the accepted
design, `docs/adr/ADR-034-online-payment-provider-routing.md` for provider
routing, and `docs/runbooks/online-payment-provider-routing.md` for testing
and recovery.
