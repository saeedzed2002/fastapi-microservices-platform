# Service Template

This is a documentation-only Phase 0 template. Phase 1 will prove an executable version through a non-domain reference service after dependency verification.

The internal style combines Clean Architecture, pragmatic Domain-Driven Design, and CQRS only where different command/query models solve a real problem. The directory names do not require separate command and query abstractions for trivial CRUD; smaller services simplify the template without weakening dependency direction or business ownership.

## Intended shape

```text
<service>/
|-- app/
|   |-- api/
|   |   `-- v1/
|   |-- application/
|   |   |-- commands/
|   |   |-- queries/
|   |   |-- handlers/
|   |   `-- dto/
|   |-- domain/
|   |   |-- entities/
|   |   |-- aggregates/
|   |   |-- value_objects/
|   |   |-- events/
|   |   |-- policies/
|   |   `-- repositories/
|   |-- infrastructure/
|   |   |-- database/
|   |   |-- kafka/
|   |   |-- celery/
|   |   |-- redis/
|   |   |-- storage/
|   |   `-- external/
|   |-- workers/
|   |-- observability/
|   |-- config/
|   |-- bootstrap/
|   `-- main.py
|-- migrations/
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- contract/
|   `-- fixtures/
|-- Dockerfile
|-- pyproject.toml
|-- README.md
`-- .env.example
```

Create only directories and adapters the service actually uses. A small context does not need empty abstractions for every platform technology.

## Dependency direction

```text
api / workers / infrastructure
              |
              v
          application
              |
              v
            domain
```

- `api/` and `workers/` are inbound delivery adapters.
- `application/` owns use-case orchestration, ports, and transaction intent.
- `domain/` owns framework-independent rules and invariants.
- `infrastructure/` implements ports for persistence, messaging, cache, storage, and providers.
- `bootstrap/` is the composition root and lifecycle wiring location.
- `observability/` configures technical instrumentation without owning business decisions.
- `config/` validates environment input and contains no business logic.

## Required runtime behavior

- `/health/live` reports process liveness without cascading optional dependency failure.
- `/health/ready` reports whether the workload can safely serve its intended traffic.
- External calls have explicit timeouts and safe retry policy.
- Shutdown stops intake/polling, drains work where possible, flushes producers, and closes connections.
- Migrations never run uncontrolled in every replica startup.
- Logs are structured and correlation/trace context propagates through all transports.

## README checklist

Every real service README states:

- purpose, responsibilities, and non-responsibilities;
- database ownership and key invariants;
- public/internal APIs;
- produced and consumed events;
- Celery tasks and queues;
- required dependencies and degradation behavior;
- local development and migration commands;
- test strategy;
- metrics, dashboards, alerts, and runbooks;
- security and authorization model.
