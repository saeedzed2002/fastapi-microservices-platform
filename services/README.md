# Services

Each child directory represents one independently deployable bounded context and owns its code, migrations, tests, contracts, image, documentation, and runtime behavior.

Planned core services are Identity, Customer, Catalog, Inventory, Cart, Order, Payment, Notification, Media, and Chat. Search and Shipping are later contexts.

## Rules

- A service never imports another service's business code.
- A service never queries another service's database.
- IDs and versioned contracts cross boundaries; domain and ORM models do not.
- A service includes only infrastructure adapters it actually needs.
- Smaller contexts may simplify the internal template without putting business logic in routes or workers.
- Every service README documents purpose, non-responsibilities, data ownership, APIs, produced/consumed events, tasks, dependencies, tests, and operations.

[`_template/README.md`](_template/README.md) documents the intended shape. `_template` is not a deployable service and is excluded from service discovery and delivery.
