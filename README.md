# FastAPI Microservices Platform

FastAPI Microservices Platform is a backend-only, production-oriented e-commerce platform built as independently deployable, event-driven microservices. The e-commerce domain is used to exercise distributed consistency, failure recovery, observability, security, and delivery practices; endpoint count is not the project goal.

## Project status

The repository is currently in **Phase 0 — Architecture & Repository Foundation**.

Phase 0 defines architecture, ownership, contracts, repository conventions, and decision records. It intentionally contains no runnable business service, dependency lockfile, Docker Compose stack, Kubernetes manifest, or Helm chart. Those artifacts begin only in their designated phases after official version and compatibility verification.

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
- [Phase 0 plan](docs/development/phase-0-plan.md)
- [Phase 1 plan](docs/development/phase-1-plan.md)

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

Phase 1 adds the verified and pinned runtime toolchain, Docker Compose infrastructure, a non-domain reference service, tests, and baseline runtime CI. See the Phase 1 plan and use scripts/platform.ps1 for repeatable local tasks.

    pwsh -File .\scripts\platform.ps1 -Task install
    pwsh -File .\scripts\platform.ps1 -Task test
    pwsh -File .\scripts\platform.ps1 -Task dev-up

## License

No license has been selected yet. License selection is a legal/product decision and will not be inferred from the technical architecture.
