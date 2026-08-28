# Identity Service

Identity-service owns user credentials and authentication sessions. It does not
own customer profiles, addresses, catalog data, orders, or another service's
database.

## Endpoints

- POST /api/v1/auth/login
- POST /api/v1/auth/otp/request
- POST /api/v1/auth/otp/verify
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- GET /api/v1/auth/me
- GET /api/v1/admin/support-agents
- POST /api/v1/admin/support-agents
- PATCH /api/v1/admin/support-agents/{support_agent_id}
- GET /health/live
- GET /health/ready
- GET /metrics

## Configuration

Customer password registration is disabled: `/api/v1/auth/register` returns
`410 Gone`. Customer registration and sign-in use the phone OTP endpoints.
`/api/v1/auth/login` accepts only active `admin` or `support_agent` users with
an email and password hash. Redis-backed failed-attempt controls apply to this
staff path and fail closed if Redis is unavailable. Customer profile contact
email remains Customer-owned and is not an Identity credential.

Create the first local administrator only through the interactive provisioning
command below. It prompts for the password, never accepts it as a command-line
argument, and refuses to overwrite an existing email:

    pwsh -NoProfile -File .\scripts\platform.ps1 -Task provision-admin -AdminEmail admin@example.com

An authenticated `admin` provisions and suspends `support_agent` accounts through
the versioned staff API. The local database records an authentication audit event
for each support-agent lifecycle change.

Copy .env.example into the deployment environment. Never commit a real JWT
secret, database credential, or `PLATFORM_INTERNAL_OTP_SHARED_SECRET`. OTP
requires the Identity Redis database, an authenticated Notification endpoint,
and the shared internal secret. It fails closed when those dependencies are
unavailable. The Kafka publisher is disabled by default.

## Migrations

    pwsh -File .\scripts\platform.ps1 -Task migrate-identity

Successful first customer OTP verification writes the customer user and an
`identity.user_registered.v2` outbox record in one transaction. The background
publisher retries broker failures and leaves the record pending until Kafka
accepts it. Raw OTP values are never published to Kafka.
