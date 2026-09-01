# Services

Each child directory represents one independently deployable bounded context and owns its code, migrations, tests, contracts, image, documentation, and runtime behavior.

Core business services are Identity, Customer, Catalog, Search, Inventory,
Cart, Order, Payment, Notification, Media, Chat, and Shipping. Shipping owns
the implemented shipment lifecycle: it creates a `READY` shipment idempotently
from an Order confirmation fact, commits authorization-bound administrator
transitions locally, and publishes its own status facts. `reference-service`
is an executable non-domain foundation probe, not a business bounded context.

## Rules

- A service never imports another service's business code.
- A service never queries another service's database.
- IDs and versioned contracts cross boundaries; domain and ORM models do not.
- A service includes only infrastructure adapters it actually needs.
- Smaller contexts may simplify the internal template without putting business logic in routes or workers.
- Every service README documents purpose, non-responsibilities, data ownership, APIs, produced/consumed events, tasks, dependencies, tests, and operations.

[`_template/README.md`](_template/README.md) documents the intended shape. `_template` is not a deployable service and is excluded from service discovery and delivery.

## Service guides

| Service | Guide |
|---|---|
| Foundation probe | [`reference-service`](reference-service/README.md) |
| Identity | [`identity-service`](identity-service/README.md) |
| Customer | [`customer-service`](customer-service/README.md) |
| Catalog | [`catalog-service`](catalog-service/README.md) |
| Search | [`search-service`](search-service/README.md) |
| Media | [`media-service`](media-service/README.md) |
| Inventory | [`inventory-service`](inventory-service/README.md) |
| Cart | [`cart-service`](cart-service/README.md) |
| Order | [`order-service`](order-service/README.md) |
| Payment | [`payment-service`](payment-service/README.md) |
| Shipping | [`shipping-service`](shipping-service/README.md) |
| Notification | [`notification-service`](notification-service/README.md) |
| Chat | [`chat-service`](chat-service/README.md) |
