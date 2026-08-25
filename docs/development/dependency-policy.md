# Dependency and Version Policy

No significant dependency, runtime, image, broker, database, CLI, SDK, or infrastructure component is introduced from memory or an old example.

## Selection rule

```text
official source
  + latest stable production-ready release
  + compatibility verification
  + security and support-lifecycle review
  + reproducible pinning
  + matching documentation
```

The highest version number is not automatically the correct version. A newer stable release may be unsuitable because of runtime support, ecosystem incompatibility, a known regression, security concerns, or migration risk.

## Required evidence

Before adoption, record:

- component and architectural purpose;
- official release source;
- stable candidate and release date;
- supported runtime/platform range and EOL status;
- relevant release and migration notes;
- compatibility with adjacent components;
- known critical issues and security advisories;
- license;
- selected version and pinning mechanism;
- reason for rejecting a newer stable candidate, if applicable;
- owner and next review date.

## Compatibility clusters

Versions are selected as compatible groups rather than isolated packages:

- Python, FastAPI, Starlette, Pydantic, Pydantic Settings, Uvicorn, and HTTP client.
- Python, SQLAlchemy, Alembic, PostgreSQL driver, and PostgreSQL.
- Kafka broker, Python Kafka client, and protocol/API compatibility.
- Python, Celery, and RabbitMQ.
- Redis server and Python Redis client.
- S3 client, MinIO, and required presigned/checksum behavior.
- OpenTelemetry API/SDK, instrumentation, exporter, Collector, and backends.
- pytest, async test support, HTTP client, Testcontainers, and Docker.
- Python base image, operating-system libraries, native dependencies, architecture, and non-root runtime.

## Reproducibility

- `pyproject.toml` declares intentional direct constraints.
- `uv.lock` records the exact resolved Python graph.
- CI uses locked synchronization and fails rather than silently changing the lock.
- Infrastructure images use verified explicit stable tags and immutable digests where practical.
- Service images are identified by service version and Git SHA/digest.
- GitHub Actions are pinned immutably after official verification.
- Documentation describes the installed versions and commands.

Unbounded image tags such as `latest`, preview releases, release candidates, EOL versions, and arbitrary broad dependency floors are prohibited by default.

## `uv` workspace decision

The intended initial candidate is one root `uv` workspace, per-service/per-library `pyproject.toml` files, and one root `uv.lock`. This matches the monorepo and provides one reproducible development/CI graph.

This is not yet an accepted runtime configuration. Phase 1 must verify current official `uv` workspace behavior and address these risks before creating it:

- a shared resolution can prevent genuinely incompatible service versions;
- one service may accidentally import a dependency installed for another;
- lock changes may be broad;
- independent image builds must include only declared service dependencies;
- shared-library changes must trigger every affected service.

If a service later requires an incompatible dependency graph, an ADR may remove it from the shared resolution. A service must never be ambiguously governed by both a root and local lockfile.

## Upgrade workflow

```text
official release review
  -> compatibility and security analysis
  -> isolated dependency change
  -> lock/image update
  -> unit, integration, contract, and E2E tests
  -> image and dependency scans
  -> documentation update
  -> reviewed merge
```

Major upgrades additionally require migration, operational-impact, coexistence, and rollback analysis. Material changes receive an ADR.
