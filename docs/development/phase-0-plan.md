# Phase 0 — Architecture & Repository Foundation

## Repository assessment

Assessment date: `2026-08-25`

- Workspace: supplied local checkout
- Official project: `FastAPI Microservices Platform`
- Official remote repository name: `fastapi-microservices-platform`
- Infrastructure namespace: `fastapi-platform`
- Initial workspace state: empty directory, no Git repository, no local `AGENTS.md`
- Decision: the supplied workspace itself is the repository root. Do not create a nested `fastapi-microservices-platform/` directory merely to match the remote repository name.

## Scope

Phase 0 establishes:

- repository identity and structure;
- architecture overview and bounded-context ownership;
- communication and consistency rules;
- ADR process and accepted baseline decisions;
- canonical event and API error envelopes;
- API, event, and service versioning policy;
- documented service template and dependency direction;
- coding, dependency, local-development, Docker, and Git conventions;
- initial system, checkout, chat, and media diagrams;
- explicit unresolved architecture questions for later phase decisions.

Phase 0 does not establish:

- a runnable FastAPI service;
- Python runtime or dependency pins;
- `uv.lock`;
- Docker Compose infrastructure;
- database schemas or migrations;
- Kafka producers/consumers;
- RabbitMQ/Celery workers;
- Redis or MinIO integrations;
- Kubernetes manifests or Helm charts;
- runtime, dependency, integration, image, or delivery CI stages;
- business APIs.

Those are Phase 1 or later responsibilities and require official version and compatibility verification immediately before introduction. Phase 0 does include a project-dependency-free structural validation script and a minimal GitHub Actions workflow pinned to an officially verified immutable action revision.

## Initial directory plan

```text
services/          independently deployable bounded contexts
libs/              small shared technical primitives
infrastructure/    Compose, Kubernetes, Helm, and platform configuration
contracts/         canonical event and OpenAPI artifacts
docs/              architecture, ADRs, diagrams, events, runbooks, development
scripts/           repeatable repository and operational commands
tests/e2e/         cross-service workflow tests
.github/workflows/ structural CI now; runtime and delivery gates with executable capabilities
```

Directories are created when they contain a purposeful artifact. Empty placeholder trees are not committed.

## Architectural assumptions

- The master specification remains the external source of truth; accepted ADRs and contracts provide its in-repository operational form.
- The local folder name does not change the official repository name or `fastapi-platform` infrastructure namespace.
- Choreography is the initial checkout Saga style; no workflow engine is introduced.
- Phase 1 will provide a non-domain reference service. It must not become a mandatory dependency of business services.
- Root `contracts/` is the canonical schema location. Future `libs/contracts` code may provide runtime validation or generated bindings but cannot become a second editable source of truth.
- User-uploaded media belongs to Media Service. Order-owned generated invoices use the same storage abstraction without transferring invoice business ownership to Media.
- Redis remains non-authoritative even where it stores externally hosted platform state.

## ADR plan

The Phase 0 baseline records decisions for:

1. monorepo and repository layout;
2. bounded contexts and database ownership;
3. synchronous REST communication;
4. Kafka domain events and topic strategy;
5. Transactional Outbox, Inbox, and idempotency;
6. RabbitMQ/Celery task execution;
7. Redis ephemeral state and chat fan-out;
8. S3-compatible object storage;
9. API, event, and service versioning;
10. Kubernetes-first runtime design.

The root/per-service `uv` workspace and lock strategy is a Phase 1 entry decision. It must be finalized during Phase 1 planning, before any `pyproject.toml` or `uv.lock` is created, using current official `uv` behavior and actual service build requirements.

## Dependency verification plan

Before any phase introduces a tool or component:

1. enumerate direct application, development, infrastructure, and image dependencies;
2. identify each official release source and support policy;
3. record the latest stable production-ready candidate and release date;
4. verify the compatibility cluster for only the components introduced in that phase;
5. review migration notes, known regressions, critical vulnerabilities, and EOL dates;
6. select the latest stable compatible version and document rejected newer candidates;
7. pin direct dependencies and important images; prefer immutable image digests for delivery;
8. generate a reproducible lockfile using the selected `uv` workspace strategy;
9. update `docs/development/toolchain.md` with evidence and exceptions;
10. validate installation, tests, image builds, and documentation against the selected versions.

No dependency version is selected merely to complete Phase 0 documentation.

## First commit plan

Proposed commit:

```text
chore: establish phase 0 architecture foundation
```

The commit should contain only architecture/repository foundation artifacts and must exclude executable platform infrastructure or unverified dependency pins.

## Exit criteria

- Project identity and namespace are consistent across documents.
- Every planned service has explicit ownership and non-ownership.
- Database ownership and transport responsibilities are unambiguous.
- Event and error envelopes have canonical machine-readable schemas.
- Baseline ADRs are accepted and indexed.
- Initial diagrams agree with written architecture.
- Dependency and version verification procedure is recorded.
- Open decisions are visible rather than silently invented.
- Repository files pass whitespace, JSON parsing, internal-link, and consistency checks available without installing dependencies.
