# Local Development Policy

## Environment profiles

The platform will support at least:

- `local`
- `test`
- `development`
- `production`

Configuration changes by environment; business rules do not.

## Phase 0 state

There is no executable local environment in Phase 0. No setup, install, migration, or infrastructure command is advertised until it exists and has been validated.

## Phase 1 target

Docker Compose will provide local PostgreSQL, Kafka, RabbitMQ, Redis, and MinIO. Observability may use a separate profile to control startup cost.

A root task runner will eventually expose short, repeatable commands conceptually equivalent to:

```text
install
lint
format
typecheck
test
dev-up
dev-down
logs
migrate SERVICE=<name>
test-service SERVICE=<name>
```

Exact commands are documented only after the selected toolchain is implemented and validated.

## Topology independence

- Services receive endpoints through configuration.
- Application code does not embed Compose hostnames or local port mappings.
- Local credentials are development-only placeholders and never reused in production.
- One local PostgreSQL instance may host logically isolated service databases.
- Durable file data uses object storage, not local application directories.
- Infrastructure failure and reset must not require restoring durable domain data from Redis.
