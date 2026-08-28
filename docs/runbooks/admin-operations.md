# Staff operations and order review runbook

## Scope

This is a backend operational API, not an administrator web panel. Identity
owns staff accounts and password authentication. Chat owns support assignment.
Order owns immutable order review. Neither Identity nor Chat reads another
service's database.

## First administrator

Create the first local `admin` only through the interactive bootstrap command:

```powershell
pwsh -NoProfile -File scripts/platform.ps1 -Task provision-admin -AdminEmail admin@example.com
```

The command asks for a password twice. Never put the password in a command-line
argument, source file, API fixture, screenshot, or commit.

## Support agents

An authenticated active `admin` uses `POST /api/v1/admin/support-agents` to
create an account whose only role is `support_agent`. `GET` lists agents and
`PATCH /api/v1/admin/support-agents/{support_agent_id}` sets `active` or
`suspended`. Every provision and status transition is stored as an Identity
authentication audit record. Suspending an agent revokes refresh sessions; an
already-issued access token expires at its normal short lifetime.

`support_agent` accounts sign in through `POST /api/v1/auth/login`, can claim
Chat support work, and cannot administer staff or inspect Orders. Only an
`admin` has the management and order-review capabilities.

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
`cursor`, then `GET /api/v1/orders/admin/{order_id}` for immutable purchase
details, transitions, and invoice state. These endpoints are intentionally
read-only: fulfilment, shipment, payment, refund, invoice-download, and
customer-profile mutation are outside their authority.
