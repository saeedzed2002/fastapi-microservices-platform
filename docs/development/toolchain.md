# Toolchain Record

Phase 0 selects only the components needed to run its structural CI gate. Runtime, application, broker, database, and deployment versions remain deliberately unselected until their target phase. Each component has an independent evidence record because compatibility and security cannot be established for a grouped technology label.

| Component | Target phase | Selection status | Evidence required before adoption |
|---|---:|---|---|
| GitHub-hosted runner | 0 | `ubuntu-24.04` managed label; verified `2026-08-25` | Supported runner label, required preinstalled shell, mutable-image update policy |
| PowerShell | 0 | Runner-provided mutable `pwsh`; minimum `7.4`; standalone `v7.6.5` reviewed `2026-08-25` but not installed | Bundled image inventory, Draft 2020-12 schema behavior, local prerequisite, mutable-image exception |
| `actions/checkout` | 0 | `v7.0.1` pinned to `3d3c42e5aac5ba805825da76410c181273ba90b1`; verified `2026-08-25` | Official release, immutable commit SHA, runtime compatibility, minimal permissions |
| Python | 1 | Not selected | Stable release, support lifecycle, platform and complete-stack compatibility |
| `uv` | 1 | Not selected | Stable release, workspace/lock behavior, Python support, reproducible installation |
| Ruff | 1 | Not selected | Python support, rule compatibility, formatter/linter behavior |
| Type checker | 1 | Not selected | Tool choice, Python/Pydantic/plugin compatibility, strictness policy |
| pytest | 1 | Not selected | Python support, plugin compatibility, asynchronous test behavior |
| pre-commit framework | 1 | Not selected | Stable release, hook revisions, reproducible local/CI behavior |
| FastAPI | 1 | Not selected | Python, Starlette, Pydantic and OpenAPI compatibility |
| Starlette | 1 | Not selected | FastAPI-supported range and security advisories |
| Pydantic | 1 | Not selected | FastAPI, settings, serialization and schema compatibility |
| Pydantic Settings | 1 | Not selected | Pydantic and configuration-source compatibility |
| Uvicorn | 1 | Not selected | Python/ASGI compatibility and production worker model |
| HTTPX | 1 | Not selected | Python, ASGI test client, timeout and transport compatibility |
| SQLAlchemy | 1 | Not selected | Python, PostgreSQL driver and Alembic compatibility |
| Alembic | 1 | Not selected | SQLAlchemy compatibility and migration behavior |
| PostgreSQL driver | 1 | Not selected | Driver choice, SQLAlchemy support, async behavior and packaging |
| PostgreSQL server/image | 1 | Not selected | Supported stable release, upgrade path, extensions, architecture and digest |
| Kafka broker/image | 1 | Not selected | Stable distribution, protocol baseline, KRaft/operations, architecture and digest |
| Kafka Python client | 1 | Not selected | Python support, broker protocol, idempotent producer and tracing integration |
| RabbitMQ server/image | 1 | Not selected | Supported stable release, Celery compatibility, quorum/DLX features and digest |
| Celery | 1 | Not selected | Python/RabbitMQ compatibility, acknowledgement, retry and shutdown semantics |
| Redis server/image | 1 | Not selected | Supported stable release, persistence/degradation policy and digest |
| Redis Python client | 1 | Not selected | Python/server compatibility, async and cluster behavior |
| S3 Python client | 1 | Not selected | Signing, checksum, multipart and presigned-request behavior |
| MinIO image | 1 | Not selected | Stable production release, S3 compatibility, architecture and digest |
| OpenTelemetry API/SDK | 1 | Not selected | Python support and semantic-convention compatibility |
| OpenTelemetry instrumentation/exporters | 1 | Not selected | FastAPI, HTTPX, SQLAlchemy, Kafka, Celery and OTLP compatibility |
| OpenTelemetry Collector image | 1 | Not selected | Stable distribution, component set, configuration compatibility and digest |
| Testcontainers | 1 | Not selected | Python/Docker compatibility and required infrastructure modules |
| Docker Engine/CLI | 1 | Not selected | Supported stable release, BuildKit/Compose compatibility and host constraints |
| Docker Compose | 1 | Not selected | Stable plugin release, specification support and local topology behavior |
| Prometheus | 1/11 | Not selected | Phase 1 minimal profile and Phase 11 production topology, image digest |
| Grafana | 1/11 | Not selected | Datasource/dashboard compatibility, image digest and security review |
| Loki | 1/11 | Not selected | Collector/export path, storage model, image digest and security review |
| Tempo | 1/11 | Not selected | OTLP/Collector compatibility, storage model and image digest |
| Kubernetes | 9 | Not selected | Supported release, version-skew policy, API lifecycle and cluster compatibility |
| `kubectl` | 9 | Not selected | Cluster version-skew compatibility and reproducible distribution |
| Helm | 10 | Not selected | Supported release, Kubernetes compatibility and chart API behavior |

## Phase 0 evidence

- GitHub documents `ubuntu-24.04` as a supported standard hosted-runner label. It is a managed, mutable environment rather than an immutable dependency; every CI run records the resolved image in its runner logs.
- The official `actions/checkout` repository marks `v7.0.1` as the current stable release verified on `2026-08-25`. The workflow pins its exact official commit SHA rather than a floating tag and grants only read access to repository contents.
- Official evidence: [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [Ubuntu 24.04 image inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md), [PowerShell `Test-Json`](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/test-json?view=powershell-7.6), [PowerShell latest release](https://github.com/PowerShell/PowerShell/releases/tag/v7.6.5), [PowerShell license](https://github.com/PowerShell/PowerShell/blob/master/LICENSE.txt), [`actions/checkout` release](https://github.com/actions/checkout/releases/tag/v7.0.1), [pinned official commit](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1), [action documentation](https://github.com/actions/checkout/blob/v7.0.1/README.md), [action manifest](https://github.com/actions/checkout/blob/v7.0.1/action.yml), [security page](https://github.com/actions/checkout/security), [license](https://github.com/actions/checkout/blob/v7.0.1/LICENSE), and [GitHub Actions security guidance](https://docs.github.com/en/code-security/tutorials/secure-your-organization/protect-against-threats).

### GitHub-hosted runner selection record

- Purpose: execute the project-dependency-free Phase 0 structural validation workflow.
- Stable candidate: the supported GA `ubuntu-24.04` x64 workflow label. `ubuntu-26.04` was still public preview and was rejected; the moving `ubuntu-latest` alias was avoided to prevent an unreviewed major operating-system switch.
- Compatibility: GitHub's maintained image inventory includes PowerShell, and the managed runner is compatible with the Node 24 runtime required by current `actions/checkout`.
- Security/support: GitHub provisions a fresh hosted environment per standard job and maintains its image. The image is mutable, so the workflow log—not repository pinning—records the exact resolved image revision for each run.
- Bundled shell exception: Phase 0 uses the runner-provided PowerShell rather than installing or pinning another copy. Microsoft documents that PowerShell `7.4` changed `Test-Json` to the JsonSchema.NET engine used for modern JSON Schema validation. The script therefore requires `7.4` or later, checks `Test-Json -SchemaFile`, and fails with a precise prerequisite message on incompatible shells. The resolved PowerShell version is part of the mutable runner-image record.
- License: not applicable to the managed runner service; bundled software licensing remains GitHub's image responsibility for this use.
- Selection/pinning: explicit service label `ubuntu-24.04`; an immutable hosted-image digest is not exposed as a workflow selector.
- Owner: platform engineering.
- Next review: before Phase 1 CI expansion or `2026-09-25`, whichever occurs first.

### PowerShell capability record

- Purpose: parse repository JSON and validate Draft 2020-12 schemas without adding a project package dependency.
- Official stable candidate: standalone PowerShell `v7.6.5`, released `2026-08-14` and marked latest when reviewed on `2026-08-25`.
- Selection: no standalone PowerShell distribution is installed or pinned by this repository. CI intentionally accepts the GitHub-managed runner version and records it on every run; local execution accepts any `pwsh` version `7.4` or later that exposes `Test-Json -SchemaFile`.
- Compatibility: Microsoft documents that PowerShell `7.4` moved `Test-Json` to JsonSchema.NET. The current repository schemas and negative in-memory cases were exercised successfully with the available `7.6.x` implementation.
- Security/support: the interpreter lifecycle and patching in CI are delegated to the supported GitHub-hosted runner image. This controlled exception avoids downloading an interpreter inside the job; it also means an image update can change behavior and must be visible in logs and caught by the schema tests.
- License: MIT.
- Owner: platform engineering.
- Next review: before Phase 1 CI expansion or `2026-09-25`, whichever occurs first.

### `actions/checkout` selection record

- Purpose: place the triggering repository revision in the Phase 0 job workspace.
- Stable candidate: `v7.0.1`, released `2026-07-20` and marked latest by the official repository when reviewed on `2026-08-25`; no newer stable candidate existed at review time.
- Release/migration notes: `v7` adds safer behavior for trusted workflow triggers, uses ESM, and updates dependencies including security fixes. The action uses Node 24 and requires Actions Runner `v2.327.1` or later; the selected GitHub-hosted runner is managed by GitHub. Self-hosted runners are outside this Phase 0 workflow.
- Compatibility: only a normal `pull_request` and `push` checkout is used. No `pull_request_target`, `workflow_run`, submodule, LFS, alternate repository, or authenticated post-checkout Git operation is required.
- Security review: the official repository listed no published security advisories at review time; this is not a guarantee that undisclosed defects do not exist. The workflow pins a full SHA, grants `contents: read`, passes no secrets, and sets `persist-credentials: false`.
- License: MIT.
- Selected pin: `3d3c42e5aac5ba805825da76410c181273ba90b1`, the verified official commit behind `v7.0.1`.
- Owner: platform engineering.
- Next review: before Phase 1 CI expansion or `2026-09-25`, whichever occurs first.

For every later selection, record the exact version or digest, verification date, release date, official source, compatibility evidence, security and license review, pinning method, exceptions, and next review date. Never populate this register from model memory, tutorials, prior repositories, or cached assumptions.
