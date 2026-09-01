# Portfolio reviewer guide

## What this repository demonstrates

This is a backend-only e-commerce platform used to demonstrate bounded
contexts, durable workflow design, operational failure behavior, and delivery
evidence. It is not a claim that a public storefront or target production
environment is currently deployed.

Use the following path for a focused review:

1. Read the [architecture overview](../architecture/overview.md) and
   [service boundaries](../architecture/service-boundaries.md). They define
   ownership before implementation details.
2. Trace the [checkout Saga](../diagrams/checkout-saga.md) and
   [Outbox/Inbox flow](../diagrams/outbox-inbox.md), then inspect the
   [checkout E2E workflow](../../tests/e2e/test_phase6_checkout_notification.py).
3. Inspect the [payment recovery model](../adr/ADR-022-zarinpal-payment-adapter-and-expiry.md)
   and the [online provider routing runbook](../runbooks/online-payment-provider-routing.md).
4. Inspect [realtime Chat](../diagrams/realtime-chat.md) and the accepted
   [support-queue assignment](../adr/ADR-019-chat-support-queue-assignment.md).
5. Trace the [Shipping ownership ADR](../adr/ADR-039-shipping-ownership-extraction.md)
   through the [Shipping command contract](../../contracts/openapi/shipping-commands.v1.openapi.json)
   and [Shipping E2E workflow](../../tests/e2e/test_phase18_shipping.py).
6. Inspect the [Kubernetes conformance ADR](../adr/ADR-028-kubernetes-conformance-ci.md)
   and the [platform workflow](../../.github/workflows/platform-ci.yml).

## Evidence map

| Claim | Primary evidence | What it proves |
|---|---|---|
| Every service owns its data and migrations | [Service boundaries](../architecture/service-boundaries.md), service-local `migrations/` directories, and [migration-head CI](../../.github/workflows/platform-ci.yml) | No cross-service database ownership is required for normal workflows. |
| Checkout tolerates duplicate delivery and partial infrastructure failure | [Checkout Saga](../diagrams/checkout-saga.md), [Outbox/Inbox ADR](../adr/ADR-005-outbox-inbox-and-idempotency.md), and [resilience E2E](../../tests/e2e/test_phase12_resilience.py) | Durable local state is committed before delivery; recovery is exercised in Compose. |
| Payment routing avoids unsafe provider failover | [Payment provider ADR](../adr/ADR-034-online-payment-provider-routing.md), [online routing plan](../development/phase-16-plan.md), and [Payment tests](../../services/payment-service/tests) | Zibal fallback occurs only after a persisted definitive Zarinpal rejection, never after an unknown outcome. |
| Customers can open support requests without exposing history to every agent | [Support assignment ADR](../adr/ADR-019-chat-support-queue-assignment.md), [Chat support contract](../../contracts/openapi/chat-support.v1.openapi.json), and [support runbook](../runbooks/chat-support-queue.md) | One eligible agent claims a durable Chat-owned request atomically; queue readers see metadata only. |
| Product feedback is bounded and moderated | [Catalog review ADR](../adr/ADR-032-catalog-product-review-moderation.md), [review contract](../../contracts/openapi/catalog-reviews.v1.openapi.json), and [moderation runbook](../runbooks/catalog-review-moderation.md) | Reviews have a one-level reply limit and explicit administrator moderation. |
| Shipment lifecycle is independently owned without opening a refund race | [Shipping ownership ADR](../adr/ADR-039-shipping-ownership-extraction.md), [Shipping command contract](../../contracts/openapi/shipping-commands.v1.openapi.json), and [Shipping E2E](../../tests/e2e/test_phase18_shipping.py) | Shipping commits an authorization-bound transition and emits a no-PII fact; Order applies the customer-facing projection only after its local fence matches. |
| Kubernetes resources are executable rather than documentation-only | [Kubernetes conformance ADR](../adr/ADR-028-kubernetes-conformance-ci.md), [conformance script](../../scripts/run_kubernetes_conformance.sh), and [workflow](../../.github/workflows/platform-ci.yml) | CI creates a disposable `Kind` cluster, applies the release path, and proves API and checkout workflow behavior in-cluster. |
| Published images pass the same security gate | [single-job publication ADR](../adr/ADR-038-single-job-ghcr-publication.md), [delivery scan-gate test](../../tests/test_ci_delivery_scan_gate.py), and [runtime image hardening test](../../tests/test_runtime_image_hardening.py) | Every exact image is built and scanned for `HIGH`/`CRITICAL` findings before one registry login or push. |

## How to reproduce evidence

For a static and unit-level check, run:

```powershell
pwsh -NoProfile -File .\scripts\validate_phase0.ps1
uv lock --check
uv run --all-packages pytest -m "not e2e" -q
```

For the complete local integration topology, follow the root
[local-development instructions](../../README.md#local-development). The
`main` workflow additionally runs Compose E2E coverage, creates a disposable
`Kind` cluster, builds exact service images, scans them, and publishes them in
one sequential `GHCR` job only after every scan succeeds.

## Scope boundaries

- There is no browser storefront. CORS stays disabled until one has a reviewed
  origin and credential policy.
- The repository does not deploy a public environment. Immutable `GHCR` image
  publication is artifact delivery, and `Kind` is disposable conformance
  evidence, not a production cluster.
- A target deployment still needs owned secrets, an ingress/TLS issuer,
  durable managed dependencies, egress controls, monitoring retention,
  access policy, and a promotion/rollback process.
- The Zarinpal and Zibal integrations use local/test configuration only; no
  claim is made that a real merchant transaction has run.
- Shipping owns the implemented shipment lifecycle, but carrier labels,
  webhooks, rate shopping, delivery estimates, address validation, returns,
  and third-party carrier integration remain out of scope.
- License selection is intentionally left to the repository owner because it
  is a legal/product decision.

## Review principle

Treat the architecture documents and canonical artifacts under `contracts/`
as the source of truth. A claim is meaningful only when it has executable or
reviewable evidence in this repository; future production concerns are
documented as boundaries rather than represented by placeholders.
