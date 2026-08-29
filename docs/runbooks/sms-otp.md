# SMS.ir customer OTP runbook

## Local configuration

Copy the repository `.env.example` to `.env`. Generate a different internal
secret for every environment, then set all values below in the ignored `.env`:

```dotenv
PLATFORM_INTERNAL_OTP_SHARED_SECRET=<at-least-32-random-characters>
NOTIFICATION_SMSIR_ENABLED=true
NOTIFICATION_SMSIR_API_KEY=<SMS.ir-api-key>
NOTIFICATION_SMSIR_LINE_NUMBER=<services-enabled-line-number>
```

Never place these values in a service `.env.example`, command history, test
fixture, source file, screenshot, issue, or Git commit.

The configured line must be services-enabled. The initial adapter uses the
`SMS.ir` Bulk endpoint because no provider template is configured. Provider
acceptance is not handset delivery confirmation; use the panel's message report
with the stored provider message ID when investigating delivery.

## Start and migrate

```powershell
pwsh -NoProfile -File scripts/platform.ps1 -Task migrate-identity
pwsh -NoProfile -File scripts/platform.ps1 -Task migrate-customer
pwsh -NoProfile -File scripts/platform.ps1 -Task migrate-notification
pwsh -NoProfile -File scripts/platform.ps1 -Task dev-up
```

The `notification-sms-worker` must be running. A missing secret or SMS
configuration deliberately produces `503` from the public OTP request endpoint;
it never falls back to a fake code or an unprotected provider call.

`platform.ps1` passes the absolute root `.env` path to Compose. This prevents
the relative-path ambiguity caused by the Compose file under
`infrastructure/compose/`. Do not replace it with a raw `docker compose`
command unless that command also supplies the root `.env` explicitly.

## Public flow

Request a code:

```http
POST /api/v1/auth/otp/request
Content-Type: application/json

{"phone":"09121234567"}
```

Verify it:

```http
POST /api/v1/auth/otp/verify
Content-Type: application/json

{"phone":"09121234567","code":"123456"}
```

The normal response is `202` for request and `200` for verification. A customer
is created only after a correct code is verified. The response contains the
normal access/refresh token pair. Staff login continues through
`POST /api/v1/auth/login` with email and password.

## Local administrator provisioning

Customer OTP does not create administrator privileges. To create the first
local administrator without adding a public registration endpoint, run:

```powershell
pwsh -NoProfile -File scripts/platform.ps1 -Task provision-admin -AdminEmail admin@example.com
```

The command prompts twice for a password and refuses to overwrite an existing
Identity email. Do not pass the password through a command-line argument,
environment variable, script, screenshot, or commit. An authenticated `admin`
provisions and manages `support_agent` accounts through the Identity API; see
the [staff operations runbook](admin-operations.md). The bootstrap command does
not change existing roles or passwords.

## Failure handling

- `429`: wait for the resend cooldown or phone request window; do not retry in a loop.
- `400`: the code is invalid, expired, or has reached the verification-attempt cap.
- `503`: restore Redis, the private Identity/Notification secret, Notification,
  RabbitMQ, or the SMS provider configuration before retrying.
- `FAILED` delivery in Notification: inspect the provider configuration and the
  worker logs. Logs must not contain the code, API key, request body, or provider
  response body.
- `SENT` means `SMS.ir` accepted the message. It is not a carrier delivery
  receipt.
