# Phase 8 Plan — Search

## Outcome

Deliver an independently deployable Search Service with a rebuildable,
eventually consistent projection of Catalog products and a public,
rate-limited product query API.

## Scope

- Search-owned `PostgreSQL` projection, Inbox, tombstones, and migration;
- durable Catalog `product.created.v1`, `product.updated.v1`, and
  `product.deleted.v1` facts through a transactional Catalog outbox;
- `Kafka` consumer with bounded retry and durable DLQ policy;
- public `GET /api/v1/search/products` with published-only visibility,
  opaque cursor, ranking, and Catalog-owned metadata filters;
- `Redis` public-search abuse limit with explicit fail-closed behavior;
- local Compose, edge routing, contracts, replay runbook, and tests.

## Non-goals

- a new dedicated search-engine runtime;
- typo correction, synonym dictionaries, autocomplete, personalised ranking,
  recommendations, or analytics;
- stock-aware search, checkout logic, or a Search-owned administrator panel;
- synchronous writes from Search to Catalog or another service database.

## Delivery sequence

1. Activate Catalog event contracts and add its transactional outbox.
2. Add Search's projection, Inbox, tombstones, full-text index, consumer, and
   rate limiter.
3. Add public API, edge route, Compose workload, migration, and recovery
   instructions.
4. Prove publication, projection, query, deletion, replay/idempotency, and
   degradation behavior with automated and local integration tests.

## Dependency selection

The phase adds no broker, datastore, image, or unbounded dependency. It uses
the existing locked `PostgreSQL`, `Kafka`, `Redis`, `aiokafka`,
`redis-py`, `FastAPI`, and `SQLAlchemy` versions. `PostgreSQL` full-text
search is selected over a new engine because the initial product has no
measured scale or relevance requirement that justifies another stateful
runtime. `Redis` uses its existing asynchronous client exclusively for the
disposable request-limit counter; it stores no projection or business truth.
