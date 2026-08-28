# Edge gateway runbook

## Scope

The local edge container is the only public entry point for versioned APIs and
the Chat WebSocket. Its canonical local address is `https://localhost:8443`.
The HTTP listener at `http://localhost:8080` redirects ordinary requests to
TLS and exposes health endpoints for container checks.

This runbook applies to local Compose only. It does not establish a production
certificate or Kubernetes ingress policy.

## Prerequisites

Generate a local certificate once per development machine:

```powershell
pwsh -NoProfile -File scripts/new_local_edge_certificate.ps1
```

The certificate and its private key are created under
`infrastructure/edge/tls/`, ignored by Git, and valid for `30` days. The
script does not replace an existing pair unless `-Force` is supplied. A
browser warning is expected until the certificate is explicitly trusted by that
developer machine.

## Start and verify

```powershell
docker compose -f infrastructure/compose/docker-compose.yml up -d --build --wait
curl.exe -k https://localhost:8443/health/ready
curl.exe -i http://localhost:8080/api/v1/reference
docker compose -f infrastructure/compose/docker-compose.yml ps edge
```

The HTTPS request returns `200`. The HTTP request returns `308` with the
canonical HTTPS location. `-k` is local-only because the certificate is
self-signed.

## Routing checks

- Call public APIs through `https://localhost:8443/api/v1/...`.
- Connect Chat through `wss://localhost:8443/api/v1/chat/ws`.
- A request to `/api/internal/` must return `404`.
- No direct host publication exists for service ports `8000` through
  `8010`.
- MinIO `9000` remains direct for presigned object bytes; Mailpit `8025`
  remains an operator/development UI.

## Diagnose

```powershell
docker compose -f infrastructure/compose/docker-compose.yml logs --no-color edge
docker compose -f infrastructure/compose/docker-compose.yml exec edge nginx -t
curl.exe -k -i https://localhost:8443/api/v1/reference
docker compose -f infrastructure/compose/docker-compose.yml config
```

- A failed TLS handshake usually means the certificate files are absent,
  expired, or unreadable by the container. Regenerate them deliberately with
  `-Force`, then recreate `edge`.
- A `502` indicates that the mapped upstream service is unavailable; inspect
  its health and logs. Do not change routing to a direct host port.
- A `429` is an edge source-IP limit. It is expected for repeated login,
  OTP/password-reset, upload, or WebSocket-upgrade attempts. Wait for the
  configured window and inspect the service-owned limit separately.
- A WebSocket failure requires checking the exact `/api/v1/chat/ws` path and
  the `Upgrade` headers; the access token still belongs in the first protocol
  frame, never in the URL.

## Recovery

After configuration or certificate changes, recreate only the edge container:

```powershell
docker compose -f infrastructure/compose/docker-compose.yml up -d --force-recreate edge
```

Do not restart stateful dependencies merely to repair edge routing. Preserve
service authorization and internal-network boundaries while diagnosing.
