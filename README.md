# FastAPI Microservices Platform

FastAPI Microservices Platform is a backend-only, production-oriented e-commerce platform built as independently deployable, event-driven microservices. The e-commerce domain is used to exercise distributed consistency, failure recovery, observability, security, and delivery practices; endpoint count is not the project goal.

## Project status

The repository has completed **Phase 18 — Shipping ownership extraction**. It
is intentionally a portfolio repository, not a deployed public environment.
Its CI publishes immutable, scanned container images as build artifacts and
proves the platform in a disposable `Kind` cluster; neither operation is a
target-environment deployment.
The local
`observability` profile collects bounded platform metrics, JSON logs, and
traces through Prometheus, Loki, Tempo, and Grafana. Resilience, staff account
recovery/device sessions, moderated catalog reviews, bounded Kubernetes
autoscaling, and Shipping-owned fulfilment transitions have durable contracts,
tests, and runbooks. Raw `Kustomize` resources remain the reviewable workload
baseline, while two Helm charts package the controlled foundation and
application-release sequence. The `main`-branch/manual CI workflow installs
those charts in a disposable `Kind` cluster, waits for controlled migrations
and workloads, then proves in-cluster API readiness and the
checkout-to-invoice-to-email and Shipping-to-Order projection workflows.
A real target environment still must provide pinned release images, secrets,
ingress/TLS, external durable services, and environment-specific egress policy
before public deployment.

## Review this repository

Start with the [portfolio reviewer guide](docs/portfolio/reviewer-guide.md).
It maps every material claim to its implementation, contract, runbook, or
executable CI evidence, and distinguishes verified local/CI behavior from
deliberately out-of-scope production operations.

## Architecture at a glance

```text
Clients
   |
   v
Edge / API Gateway
   |
   v
FastAPI Microservices
   |-- service-owned PostgreSQL databases
   |-- Transactional Outbox -> Kafka domain events
   |-- RabbitMQ -> bounded-context Celery workers
   |-- Redis cache / rate limits / presence / WebSocket fan-out
   `-- S3-compatible object storage (MinIO initially)
```

The platform follows these non-negotiable rules:

- Every service is a bounded context and owns its durable data and migrations.
- A service never queries another service's database.
- REST is used for synchronous request/response interactions.
- Kafka transports durable domain facts: **what happened**.
- RabbitMQ and Celery transport executable work: **what needs to be done**.
- Redis is disposable and never the source of truth for durable business data.
- Critical domain events use a Transactional Outbox; consumers are idempotent and use an Inbox or equivalent durable deduplication.
- Binary files live in S3-compatible object storage, behind an `ObjectStorage` abstraction.
- API, event schema, and service/container versions evolve independently.
- Application workloads must be designed Kubernetes-first even while local development uses Docker Compose.

## Planned services

Core bounded contexts:

- `identity-service`
- `customer-service`
- `catalog-service`
- `search-service`
- `inventory-service`
- `cart-service`
- `order-service`
- `payment-service`
- `notification-service`
- `media-service`
- `chat-service`

Incremental bounded-context extraction:

- `shipping-service` — owns a `READY` shipment created idempotently from `order.confirmed.v1`, administrator lifecycle commands, its own transition audit, and its own `Outbox`. Every command obtains an Order-owned short-lived authorization; an expired authorization is reconciled from Shipping before a refund can proceed. `Compose` and `Kind` register its API, migration, and dedicated event worker; the shared checkout-to-Shipping workflow proves the asynchronous Order projection.

See [service boundaries](docs/architecture/service-boundaries.md) for ownership and non-ownership rules.

## Repository map

- `services/` — independently deployable bounded contexts and the documented service template.
- `libs/` — small cross-cutting technical primitives; never shared domain models.
- `contracts/` — canonical event and API contract artifacts.
- `infrastructure/` — local and deployment infrastructure, introduced incrementally.
- `docs/` — architecture, ADRs, diagrams, events, runbooks, and development policy.
- `scripts/` — repeatable developer and operational automation.
- `tests/e2e/` — cross-service workflow tests introduced with executable services.
- `.github/workflows/` — CI/CD workflows introduced as corresponding capabilities exist.

The complete intended layout is documented in [repository structure](docs/architecture/repository-structure.md).

## Documentation

- [Architecture overview](docs/architecture/overview.md)
- [Communication and consistency](docs/architecture/communication-and-consistency.md)
- [Service boundaries](docs/architecture/service-boundaries.md)
- [Security baseline](docs/architecture/security-baseline.md)
- [Observability](docs/architecture/observability.md)
- [Architecture diagrams](docs/diagrams/README.md)
- [Open architectural questions](docs/architecture/open-questions.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Portfolio reviewer guide](docs/portfolio/reviewer-guide.md)
- [Event contracts](docs/events/README.md)
- [Coding standards](docs/development/coding-standards.md)
- [Dependency and version policy](docs/development/dependency-policy.md)
- [Testing strategy](docs/development/testing-strategy.md)
- [CI/CD strategy](docs/development/ci-cd.md)
- [Invoice and notification runbook](docs/runbooks/invoice-notification.md)
- [SMS OTP runbook](docs/runbooks/sms-otp.md)
- [Staff operations runbook](docs/runbooks/admin-operations.md)
- [Search projection runbook](docs/runbooks/search-projection.md)
- [Edge gateway runbook](docs/runbooks/edge-gateway.md)
- [Kubernetes deployment runbook](docs/runbooks/kubernetes-deployment.md)
- [Helm delivery charts](infrastructure/helm/README.md)
- [Online payment provider routing runbook](docs/runbooks/online-payment-provider-routing.md)
- [Phase 0 plan](docs/development/phase-0-plan.md)
- [Phase 1 plan](docs/development/phase-1-plan.md)
- [Phase 2 plan](docs/development/phase-2-plan.md)
- [Phase 4 plan](docs/development/phase-4-plan.md)
- [Phase 5 plan](docs/development/phase-5-plan.md)
- [Phase 6 plan](docs/development/phase-6-plan.md)
- [Phase 7 plan](docs/development/phase-7-plan.md)
- [Phase 8 plan](docs/development/phase-8-plan.md)
- [Phase 9 plan](docs/development/phase-9-plan.md)
- [Phase 10 plan](docs/development/phase-10-plan.md)
- [Phase 11 plan](docs/development/phase-11-plan.md)
- [Phase 12 plan](docs/development/phase-12-plan.md)
- [Phase 13 plan](docs/development/phase-13-plan.md)
- [Phase 14 plan](docs/development/phase-14-plan.md)
- [Phase 15 plan](docs/development/phase-15-plan.md)
- [Phase 16 plan](docs/development/phase-16-plan.md)
- [Phase 17 plan](docs/development/phase-17-plan.md)
- [Phase 18 plan](docs/development/phase-18-plan.md)
- [Phase 19 plan](docs/development/phase-19-plan.md)

## Roadmap

| Phase | Outcome |
|---|---|
| 0 | Architecture & Repository Foundation |
| 1 | Platform Foundation |
| 2 | Identity & Customer |
| 3 | Catalog & Media |
| 4 | Inventory & Cart |
| 5 | Order & Payment |
| 6 | Invoice & Notification |
| 7 | Realtime Chat |
| 8 | Search |
| 9 | Kubernetes |
| 10 | Helm |
| 11 | Complete Observability |
| 12 | Hardening |
| 13 | Staff password reset & device sessions |
| 14 | Catalog reviews, replies & moderation |
| 15 | Kubernetes API autoscaling |
| 16 | Online payment provider routing |
| 17 | Portfolio evidence and reviewer guide |
| 18 | Shipping ownership extraction |
| 19 | In progress: Post-delivery returns and refund lifecycle |

## Local development

The local edge gateway is the only public API entry point: use
`https://localhost/api/v1/...` and `wss://localhost/api/v1/chat/ws`.
Local Swagger interfaces are available at `https://localhost/docs/` only;
they are not a production ingress feature.
Generate its ignored self-signed certificate once before `dev-up` with
`pwsh -NoProfile -File .\\scripts\\new_local_edge_certificate.ps1`. The HTTP
listener `http://localhost` redirects to TLS. API services no longer publish host ports;
MinIO `9000` and the Mailpit UI `8025` remain direct local development endpoints.
`dev-up` first builds API images and then starts Compose; this lets
the Invoice and Notification workers consume the same built service images.
Run Docker Compose directly from the repository root. The ignored root `.env`
sets `COMPOSE_FILE` to the canonical Compose configuration, so no `--env-file`
or `-f` argument is needed.

    pwsh -File .\scripts\platform.ps1 -Task install
    pwsh -File .\scripts\platform.ps1 -Task test
    pwsh -NoProfile -File .\scripts\new_local_edge_certificate.ps1
    docker compose up -d --build

For the optional local telemetry stack, follow the
[observability profile](infrastructure/observability/README.md). It is not a
production deployment.
    docker compose stop
    docker compose start
    docker compose up -d --force-recreate
    pwsh -File .\scripts\platform.ps1 -Task migrate-identity
    pwsh -File .\scripts\platform.ps1 -Task migrate-customer
    pwsh -File .\scripts\platform.ps1 -Task migrate-catalog
    pwsh -File .\scripts\platform.ps1 -Task migrate-media
    pwsh -File .\scripts\platform.ps1 -Task migrate-inventory
    pwsh -File .\scripts\platform.ps1 -Task migrate-cart
    pwsh -File .\scripts\platform.ps1 -Task migrate-order
    pwsh -File .\scripts\platform.ps1 -Task migrate-payment
    pwsh -File .\scripts\platform.ps1 -Task migrate-notification
    pwsh -File .\scripts\platform.ps1 -Task migrate-chat
    $env:RUN_E2E = "1"; uv run pytest tests/e2e/test_phase6_checkout_notification.py

For ordinary local shutdown and restart, use `docker compose stop` and
`docker compose start`; they retain the existing containers and their
environment. After changing `.env` or Compose configuration, use
`docker compose up -d --force-recreate`. `docker compose down` removes the
containers. `scripts/platform.ps1` remains available as an optional task runner.

## License

No license has been selected yet. License selection is a legal/product decision and will not be inferred from the technical architecture.
