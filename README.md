# FastAPI Microservices Platform

FastAPI Microservices Platform is a backend-only, production-oriented e-commerce platform built as independently deployable, event-driven microservices. The e-commerce domain is used to exercise distributed consistency, failure recovery, observability, security, and delivery practices; endpoint count is not the project goal.

## Project status

The repository is currently in **Phase 7 — Realtime Chat**, with customer
phone-OTP authentication being completed before the later Search phase.

The current increment adds a customer OTP flow that keeps raw codes in
Identity-owned temporary Redis state, dispatches SMS through Notification's
durable task intent and Celery worker, and keeps administrator email/password
authentication separate. It uses the configured `SMS.ir` Bulk adapter only
after a local secret configuration is supplied.

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
- `inventory-service`
- `cart-service`
- `order-service`
- `payment-service`
- `notification-service`
- `media-service`
- `chat-service`

Later bounded contexts:

- `search-service`
- `shipping-service`

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
- [Event contracts](docs/events/README.md)
- [Coding standards](docs/development/coding-standards.md)
- [Dependency and version policy](docs/development/dependency-policy.md)
- [Testing strategy](docs/development/testing-strategy.md)
- [CI/CD strategy](docs/development/ci-cd.md)
- [Invoice and notification runbook](docs/runbooks/invoice-notification.md)
- [SMS OTP runbook](docs/runbooks/sms-otp.md)
- [Edge gateway runbook](docs/runbooks/edge-gateway.md)
- [Phase 0 plan](docs/development/phase-0-plan.md)
- [Phase 1 plan](docs/development/phase-1-plan.md)
- [Phase 2 plan](docs/development/phase-2-plan.md)
- [Phase 4 plan](docs/development/phase-4-plan.md)
- [Phase 5 plan](docs/development/phase-5-plan.md)
- [Phase 6 plan](docs/development/phase-6-plan.md)
- [Phase 7 plan](docs/development/phase-7-plan.md)

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
Use `scripts/platform.ps1` for repeatable local tasks.

    pwsh -File .\scripts\platform.ps1 -Task install
    pwsh -File .\scripts\platform.ps1 -Task test
    pwsh -NoProfile -File .\scripts\new_local_edge_certificate.ps1
    pwsh -File .\scripts\platform.ps1 -Task dev-up
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

## License

No license has been selected yet. License selection is a legal/product decision and will not be inferred from the technical architecture.
