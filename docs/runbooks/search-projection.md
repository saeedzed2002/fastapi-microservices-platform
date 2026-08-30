# Search projection recovery

## Scope

Search is a rebuildable projection, not the source of truth for product,
price, stock, or publication state. The normal public query is
`GET /api/v1/search/products?q=<query>`. Catalog remains authoritative when a
Search result appears stale.

## Detection

Investigate when Search readiness returns `503`, a recently published product
is absent beyond normal event-delivery delay, a deleted product remains
visible, or the Search consumer writes a record to the Kafka DLQ. Correlate by
Catalog product ID and event ID only; never put bearer tokens or customer data
in tickets or logs.

## Existing local volumes

The Compose initialization script creates `search_service` for new local
volumes. If PostgreSQL already existed before Phase 8, create the isolated
local role and database once, then apply the migration:

```powershell
docker compose --env-file .env -f infrastructure/compose/docker-compose.yml exec postgres `
  psql -U platform -d postgres -c "CREATE ROLE search_service LOGIN PASSWORD 'search-local-only';"
docker compose --env-file .env -f infrastructure/compose/docker-compose.yml exec postgres `
  psql -U platform -d postgres -c "CREATE DATABASE search_service OWNER search_service;"
pwsh -NoProfile -File scripts/platform.ps1 -Task migrate-search
```

If the role or database already exists, PostgreSQL returns an expected conflict;
do not drop an existing database merely to repeat this setup.

## Rebuild

Rebuild only the Search projection after confirming that Catalog topic history
contains the required recovery window. This does not change Catalog products.

1. Stop `search-service` so its consumer group becomes inactive.
2. Empty only the `search_documents`, `search_tombstones`, and
   `inbox_messages` tables in the `search_service` database.
3. Reset the `search-service.catalog` group for
   `fastapi-platform.catalog.events.v1` to the earliest offset.
4. Start `search-service` and wait for readiness and the expected projection.

```powershell
docker compose --env-file .env -f infrastructure/compose/docker-compose.yml stop search-service
docker compose --env-file .env -f infrastructure/compose/docker-compose.yml exec postgres `
  psql -U search_service -d search_service -c "TRUNCATE search_documents, search_tombstones, inbox_messages;"
docker compose --env-file .env -f infrastructure/compose/docker-compose.yml exec kafka `
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 `
  --group search-service.catalog --topic fastapi-platform.catalog.events.v1 `
  --reset-offsets --to-earliest --execute
docker compose --env-file .env -f infrastructure/compose/docker-compose.yml start search-service
```

Do not reset offsets while the consumer is running. If a Catalog topic's
retention has expired, do not invent Search records; restore Catalog event
history from the approved backup/recovery process before rebuilding.

## Failure policy

`Redis` backs the public per-source-IP request limit. If it is unavailable,
Search returns `503` and readiness is not healthy. This is deliberate:
canonical Catalog, checkout, payment, and administrative operations remain
available while the public search abuse control is restored.
