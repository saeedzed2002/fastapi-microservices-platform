# Repository Structure

The official remote repository name is `fastapi-microservices-platform`. A local checkout may use a different folder name and must not contain a redundant nested repository directory merely to match the remote name.

## Intended layout

```text
fastapi-microservices-platform/
|-- services/
|-- libs/
|-- infrastructure/
|-- contracts/
|   |-- events/
|   `-- openapi/
|-- docs/
|   |-- architecture/
|   |-- adr/
|   |-- diagrams/
|   |-- events/
|   |-- runbooks/
|   `-- development/
|-- scripts/
|-- tests/
|   `-- e2e/
|-- .github/
|   `-- workflows/
|-- README.md
|-- CONTRIBUTING.md
|-- AGENTS.md
|-- .editorconfig
|-- .gitattributes
`-- .gitignore
```

Runtime configuration such as `pyproject.toml`, `uv.lock`, `.env.example`, `Makefile`, `docker-compose.yml`, and service Dockerfiles is introduced only when the relevant implementation exists and its versions have been officially verified. Phase 0 includes only an executable structural-validation workflow; runtime CI stages arrive with executable code. Empty or misleading configuration files are not used to simulate progress.

## Directory ownership

### `services/`

Each child is an independently deployable bounded context. A service owns its application code, migrations, tests, image, README, API, events, database, and workers.

Services may share a repository but must not rely on source imports from another service.

### `libs/`

Contains small technical primitives such as event-envelope validation, logging/context helpers, test support, and generic platform adapters.

Forbidden examples include shared `Product`, `Order`, `Payment`, `User`, or other domain entities. Shared business models create semantic coupling and synchronized deployment.

### `contracts/`

Contains canonical machine-readable API and event artifacts. This directory is the editable source of truth for cross-service schemas.

Future code under `libs/contracts` may validate or generate language bindings from these artifacts. It must not contain an independently maintained competing schema.

### `infrastructure/`

Contains infrastructure configuration grouped by concern:

- Compose and local dependencies;
- PostgreSQL, Kafka, RabbitMQ, Redis, and MinIO configuration;
- observability collection and dashboards;
- Kubernetes resources;
- Helm charts after Kubernetes resources stabilize.

Application code depends on protocols and configuration, not on this directory's deployment topology.

### `docs/`

Contains architecture, accepted decisions, diagrams, event catalogues, runbooks, and developer policy. Documentation changes in the same commit as behavior or version-sensitive configuration changes.

### `scripts/`

Contains repeatable commands that reduce manual setup and operational error. Scripts must be non-interactive where practical, scoped, documented, and safe to rerun.

### `tests/e2e/`

Contains workflows that span service boundaries. Unit, integration, and contract tests remain owned by each service.

### `.github/workflows/`

Contains CI/CD workflows. The suite grows incrementally but eventually validates format, lint, types, unit/integration/contract tests, images, dependencies, containers, migrations, rollout, readiness, and smoke behavior as applicable.

## Service layout

The documented template is under [`services/_template/README.md`](../../services/_template/README.md). Smaller services may simplify it, but dependency direction and boundary rules remain mandatory.
