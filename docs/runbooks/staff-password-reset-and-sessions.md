# Staff password reset and device sessions

## Scope and prerequisites

This runbook applies only to an existing active Identity user with the `admin`
role and a password hash. Customers authenticate with phone OTP; they must not
use this workflow.

Configure both services with the same non-empty
`PLATFORM_INTERNAL_OTP_SHARED_SECRET` when using Compose. Configure
`IDENTITY_SESSION_METADATA_HMAC_SECRET` with a separate random value of at
least `32` characters. Identity needs reachable Redis and Notification needs a
working SMTP target for actual email delivery. These values are examples only;
do not commit a real secret.

## Reset sequence

1. Request a reset. The `202` response is intentionally identical for every
   account state and does not prove that an email will be sent.

```powershell
$baseUrl = "https://localhost"
Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/password-reset/request" `
  -ContentType "application/json" `
  -Body '{"email":"admin@example.test"}'
```

2. Retrieve the one-time token from the configured local mail sink. Do not
   paste it into an issue, log, commit, or shell history.

3. Submit the token and a replacement password. A successful response is
   `204`; all refresh sessions for that user are revoked.

```powershell
Invoke-WebRequest -Method Post -Uri "$baseUrl/api/v1/auth/password-reset/confirm" `
  -ContentType "application/json" `
  -Body '{"token":"<one-time-token>","new_password":"replace-with-12-or-more-characters"}'
```

4. Sign in again through `POST /api/v1/auth/login`. An old access token may
   remain usable for its bounded lifetime; its old refresh token cannot create
   a new session.

## Session inventory and revocation

Use a fresh access token as a Bearer credential. The API lists only active
sessions owned by that user and exposes a bounded user agent, timestamps, and a
session ID. It deliberately does not expose a raw IP address or identify the
current refresh session.

```powershell
$headers = @{ Authorization = "Bearer <access-token>" }
Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/sessions" -Headers $headers
Invoke-WebRequest -Method Delete -Uri "$baseUrl/api/v1/auth/sessions/<session-id>" -Headers $headers
Invoke-WebRequest -Method Post -Uri "$baseUrl/api/v1/auth/sessions/revoke-all" -Headers $headers
```

## Failure behavior

- If Identity Redis is unavailable, reset creation and the worker's raw-token
  retrieval fail closed. No valid reset credential is issued.
- If the Notification handoff cannot be confirmed, Identity consumes the reset
  request and removes the temporary raw token before returning `503`.
- If SMTP fails after task dispatch, Notification records a generic failed
  delivery and retries; it does not persist the raw token.
- Reusing a revoked refresh token whose stored hash still matches causes all
  currently active sessions in that token family to be revoked. The API still
  returns only generic `401`.
