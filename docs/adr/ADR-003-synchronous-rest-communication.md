# ADR-003 — Use REST for initial synchronous service communication

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Some operations require an immediate response or authoritative current read. The initial platform does not have measured requirements that justify multiple synchronous protocols.

## Decision

Use versioned REST APIs for initial client and service-to-service synchronous communication. Use HTTPX or another officially selected compatible client behind application ports when Phase 1 introduces runtime dependencies.

Do not keep a database transaction open during a network call. Define timeouts and bounded retries; unsafe commands are not retried automatically without idempotency.

Do not introduce gRPC until benchmarks or contract requirements justify it through a new ADR.

## Consequences

### Positive

- One familiar protocol and OpenAPI contract model.
- Straightforward debugging and gateway integration.
- Lower early platform complexity.

### Negative and risks

- HTTP calls create temporal coupling.
- Chatty request chains can reduce availability and increase latency.
- JSON payloads may be less efficient than binary RPC for future high-volume paths.

## Alternatives considered

- gRPC from the start: deferred because no measured latency, streaming, or strongly typed RPC requirement justifies a second synchronous protocol.
- Direct database access: rejected because it bypasses service ownership and creates schema coupling.
- Kafka for every interaction: rejected because asynchronous facts cannot provide every immediate command/query result.

## Compatibility and migration

Initial APIs begin at `/api/v1`. Breaking HTTP changes require a separately exposed version and a consumer migration window. Introducing gRPC or another synchronous protocol requires measured evidence, a new ADR, and coexistence during migration.

## Validation

- Contract tests detect breaking OpenAPI changes.
- Integration tests cover timeout, unavailable dependency, and idempotent retry behavior.
- Traces propagate through HTTP headers.

## Related material

- [Communication and consistency](../architecture/communication-and-consistency.md)
- [Service template](../../services/_template/README.md)
