# ADR-025: Rebuildable Catalog search projection

- Status: Accepted
- Date: 2026-08-30
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

Catalog is the canonical owner of products, categories, prices, variants, and
publication state. Its direct listing endpoint is intentionally not a search
index and cannot safely become one without coupling search ranking, public
abuse controls, and eventual-consistency recovery to Catalog's write path.

The platform needs public product search while preserving service ownership,
durable delivery, replay recovery, and the existing `PostgreSQL`, `Kafka`, and
`Redis` deployment baseline. The initial product does not have measured
relevance, synonym, autocomplete, or scale requirements that justify adding a
second search-engine runtime.

## Decision

Introduce Search as an independently deployable service with its own
`search_service` database. It owns only a rebuildable projection of Catalog
product fields needed for public discovery: identifier, slug, name,
description, publication state, category, brand, price, currency, attributes,
and source update timestamp. It never reads Catalog's database or owns Catalog
truth.

Catalog writes `product.created.v1`, `product.updated.v1`, and
`product.deleted.v1` into a transactional outbox in the same transaction as
the canonical product mutation. A Catalog migration creates initial
`product.created.v1` outbox rows for existing products. Search consumes the
Catalog topic with a stable consumer group, records an Inbox row in the same
transaction as the projection mutation, and keeps deletion tombstones so an
older replayed update cannot recreate a deleted product.

Search uses `PostgreSQL` generated `tsvector` columns and a `GIN` index with
the `simple` configuration, plus a bounded substring fallback for partial
matches. It exposes only `GET /api/v1/search/products`. Results include only
published products and use a bounded opaque offset cursor. Optional filters
are category, brand, currency, and price range; stock, carts, orders, and
Media bytes remain outside the projection.

The public endpoint has an edge request limit and a service-owned,
Redis-backed, source-IP limit. Redis failure returns `503` rather than silently
removing abuse protection. Search is non-critical and can fail closed while
Catalog, checkout, and payment remain available.

Recovery is an operator-controlled replay: stop the Search consumer, reset
the Search consumer group to the earliest Catalog offset, and restart against
an empty Search projection. The Catalog bootstrap outbox and all later product
events follow the same delivery path.

## Consequences

### Positive

- Search queries do not load or lock Catalog's canonical tables.
- Product mutations and their Search facts are durable together.
- The projection is disposable and recoverable from `Kafka` without an
  undocumented cross-database repair path.
- Public search excludes drafts even when Search has already consumed their
  creation event.
- No new broker, database, or search-engine runtime is introduced.

### Negative and risks

- Results are eventually consistent with Catalog publication and deletion.
- `PostgreSQL` full-text search has deliberately basic relevance; typo
  tolerance, synonyms, autocomplete, and language-specific stemming require
  measured requirements and a later ADR.
- A rebuild depends on retained Catalog topic history. Operators must preserve
  topic retention appropriate to the required recovery window.
- Redis loss makes public search unavailable by design, but does not affect
  canonical Catalog or checkout workflows.

## Alternatives considered

- Query Catalog directly for every public search: rejected because it would
  turn Catalog's write database into the public relevance and abuse-control
  path, and would not provide an independent rebuildable projection.
- Add Elasticsearch or OpenSearch now: rejected because no scale or relevance
  evidence justifies a new stateful runtime, operational surface, and client
  dependency for the initial product.
- Maintain Search synchronously inside Catalog: rejected because it breaks the
  bounded-context ownership and couples Catalog availability to a derived read
  model.
- Fail open when Redis is unavailable: rejected because public search abuse
  controls would silently disappear.

## Compatibility and migration

The reserved Catalog event names become active with versioned payload schemas.
No existing emitted event changes. Catalog migration
`0003_search_events_outbox` introduces the transactional outbox and enqueues
an initial product snapshot for existing records. Search migration
`0001_search_projection` creates only Search-owned projection, tombstone, and
Inbox tables.

The public API is new under `/api/v1`; no existing endpoint changes semantic
behavior. Catalog gains an administrator-only product deletion command so the
active deletion event has a canonical producer.

## Validation

- Unit tests cover cursor validation, public rate-limit key privacy, and the
  public OpenAPI route.
- Catalog tests cover event creation with product mutations and administrator
  product deletion.
- Contract validation covers active event payload schemas and Search's OpenAPI
  artifact.
- Local integration proves initial Catalog outbox publication, Search consumer
  projection, public query visibility, draft exclusion, deletion, replay-safe
  idempotency, and Redis/`Kafka` readiness.

## Related material

- Contracts: `contracts/catalog.json`, `contracts/events/`, and
  `contracts/openapi/search-query.v1.openapi.json`
- Runbook: `docs/runbooks/search-projection.md`
- Plan: `docs/development/phase-8-plan.md`
