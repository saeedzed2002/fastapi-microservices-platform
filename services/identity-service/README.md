# Identity Service

Identity-service owns user credentials and authentication sessions. It does not
own customer profiles, addresses, catalog data, orders, or another service's
database.

## Endpoints

- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- GET /api/v1/auth/me
- GET /health/live
- GET /health/ready
- GET /metrics

## Configuration

Copy .env.example into the deployment environment. Never commit a real JWT
secret or database credential. The Kafka publisher is disabled by default.

## Migrations

    pwsh -File .\scripts\platform.ps1 -Task migrate-identity

The service writes the user and identity.user_registered.v1 outbox record in one
transaction. The background publisher retries broker failures and leaves the
record pending until Kafka accepts it.
