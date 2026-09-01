# Staff operations and order review runbook

## Scope

This is a backend operational API, not an administrator web panel. Identity
owns the two-role account model and password authentication for administrators.
Chat owns support assignment. Order owns order review, fulfillment, and
refund-request state. Neither Identity nor Chat reads another service's database.

## First administrator

Create the first local `admin` only through the interactive bootstrap command:

```powershell
pwsh -NoProfile -File scripts/platform.ps1 -Task provision-admin -AdminEmail admin@example.com
```

The command asks for a password twice. Never put the password in a command-line
argument, source file, API fixture, screenshot, or commit.

## Roles

The initial platform has exactly two roles: `customer` and `admin`. Customers
authenticate with phone OTP. Only an `admin` can use password login and all
privileged catalog, inventory, support-queue, and Order operations. There is no
public role-assignment API in this release.

## Staff-login abuse control

Identity records failed staff password attempts in Redis under a SHA-256 email
digest, never a raw email or password. The defaults are `5` failures in `900`
seconds, followed by a `900` second lockout. Redis loss fails this login path
closed with `503`; it does not affect customer OTP state or issued access
tokens. The local edge supplies a separate source-IP limit and does not replace
this control.

Use `Retry-After` from a `429` response; do not retry in a loop. Adjust the
explicit Compose environment values only after recording a security review:

```dotenv
IDENTITY_STAFF_LOGIN_MAX_FAILURES=5
IDENTITY_STAFF_LOGIN_FAILURE_WINDOW_SECONDS=900
IDENTITY_STAFF_LOGIN_LOCKOUT_SECONDS=900
```

## Customer profile and orders

The customer saves `email` through `PUT /api/v1/customers/me` before checkout.
The address remains Customer-owned. A successful checkout records an immutable
email and address snapshot in Order. Customer history is `GET /api/v1/orders`
with an opaque cursor. A customer can retrieve only an owned order.

An `admin` uses `GET /api/v1/orders/admin` with optional `status`, `limit`, and
`cursor`, then `GET /api/v1/orders/admin/{order_id}` for purchase details,
transitions, invoice state, fulfillment, and a refund-request identifier.

Use `PATCH /api/v1/orders/admin/{order_id}/fulfillment` only in the legal
sequence `CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED`. A `SHIPPED` update
must include both `carrier` and `tracking_number`.

Use `POST /api/v1/orders/admin/{order_id}/refund` with a fresh
`Idempotency-Key` only for a `CONFIRMED` Zarinpal order. It returns `202` and
the order becomes `REFUND_PENDING`; Payment later emits the result. Do not
ship while it is pending and do not claim a refund is complete before the order
reaches `REFUNDED`.

## Delivered-order returns

Do not use the generic refund command for a delivered order. The owning
customer creates one full-order request at `POST /api/v1/orders/{order_id}/returns`.
An `admin` lists `GET /api/v1/orders/admin/returns`, records an idempotent
approval or rejection, and records receipt only after merchandise is physically
received. Receipt dispatches the independent Inventory and Payment handoffs.

For `REFUND_FAILED`, preserve the return and receipt audit, reconcile the
provider settlement, and record the customer-support outcome. Never retry a
receipt/refund command with a new idempotency key or alter Order, Payment, or
Inventory rows manually. See [post-delivery return reconciliation](post-delivery-returns.md).
