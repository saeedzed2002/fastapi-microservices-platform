# Phase 1 — Platform Foundation

Phase 1 turns the architecture-only repository into a small, runnable platform baseline without introducing business-domain services.

## Delivered foundation

- Root uv workspace and reproducible uv.lock.
- A dependency-light reference-service proving configuration, JSON logs, request/correlation headers, health endpoints, metrics, OpenAPI, tests, and a non-root container image.
- Local Docker Compose topology for PostgreSQL, Kafka, RabbitMQ, Redis, MinIO, and the reference service.
- Logical reference_service PostgreSQL database owned by a separate database role.
- Repeatable PowerShell tasks in scripts/platform.ps1.
- Pull-request CI for locked dependency sync, lint, format, type checking, tests, Compose validation, and container build.

## Explicit non-goals

Phase 1 does not implement business services, migrations for business domains, Kafka domain events, Celery workloads, Kubernetes manifests, Helm charts, production observability backends, or production secrets.

## Acceptance checks

    uv sync --locked --all-packages
    uv run --all-packages pytest
    uv run --all-packages ruff check .
    uv run --all-packages ruff format --check .
    uv run --all-packages mypy
    docker compose -f infrastructure/compose/docker-compose.yml config
    docker build -f services/reference-service/Dockerfile .

## Version evidence

Selections are recorded in docs/development/toolchain.md. The official Apache Kafka download page lists 4.2.0 as the current stable release at selection time; official Docker Hub pages list the selected PostgreSQL, RabbitMQ, and Redis image tags. MinIO's official container documentation identifies the selected release used by the local image.
