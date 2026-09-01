# Customer Service

Customer-service owns customer profiles, contact email, and addresses keyed by
the identity user ID. It does not own passwords, refresh sessions, identity
tables, or catalog/order data.

## Endpoints

- GET /api/v1/customers/me
- PUT /api/v1/customers/me
- GET /api/v1/customers/me/addresses
- POST /api/v1/customers/me/addresses
- PATCH /api/v1/customers/me/addresses/{address_id}
- DELETE /api/v1/customers/me/addresses/{address_id}
- GET /health/live
- GET /health/ready
- GET /metrics

## Configuration

Copy .env.example into the deployment environment. The Kafka consumer is
disabled by default and can be enabled after Kafka and the identity migration
are available.

## Migrations

    pwsh -File .\scripts/platform.ps1 -Task migrate-customer

The consumer creates or updates one local profile from each
`identity.user_registered.v1` or `identity.user_registered.v2` event. The
phone-only `v2` payload has no email address. Reprocessing either event does
not create a second profile because the identity user ID is the customer
primary key.

Every profile and address endpoint requires the `customer` role. The optional
contact email is normalized locally and is not an Identity login credential.
Order obtains it only through the authenticated checkout snapshot contract.

## Verification

Run focused checks with
`uv run --package customer-service pytest services/customer-service/tests -q`.
The service exposes `GET /health/live`, `GET /health/ready`, and `GET /metrics`;
readiness checks its local PostgreSQL database only. Customer has no Celery
worker in this phase.
