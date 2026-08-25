# Event Catalogue and Policy

The machine-readable registry is [`contracts/catalog.json`](../../contracts/catalog.json). The canonical envelope is [`event-envelope.v1.schema.json`](../../contracts/events/event-envelope.v1.schema.json).

## Naming

Event names use lower-case past-tense domain facts with an explicit schema version:

```text
<aggregate-or-concept>.<fact>.v<version>
```

Examples:

- `order.created.v1`
- `inventory.reserved.v1`
- `inventory.reservation_failed.v1`
- `payment.succeeded.v1`
- `media.ready.v1`

Commands and Celery task names are not domain events.

## Initial reserved events

| Event | Owner | Expected consumers | Phase |
|---|---|---|---|
| `order.created.v1` | Order | Inventory | 5 |
| `inventory.reserved.v1` | Inventory | Order, Payment | 5 |
| `inventory.reservation_failed.v1` | Inventory | Order | 5 |
| `payment.succeeded.v1` | Payment | Order | 5 |
| `payment.failed.v1` | Payment | Order, Inventory | 5 |
| `order.confirmed.v1` | Order | Order invoice dispatcher | 6 |
| `invoice.generated.v1` | Order | Notification | 6 |
| `media.ready.v1` | Media | Asset-owning contexts | 3+
| `product.created.v1` | Catalog | Search | 8 |
| `product.updated.v1` | Catalog | Search | 8 |
| `product.deleted.v1` | Catalog | Search | 8 |

These names are reserved architecture vocabulary. Their payload contracts remain unavailable until the owning phase designs aggregates, authorization, idempotency, privacy, and consumer needs.

## Compatibility and retirement

- A breaking payload or semantic change creates a new `.vN` event.
- Compatible additive changes remain optional for older consumers.
- Producers and consumers document a migration window before retirement.
- Replayed historical records remain valid under the schema version they were written with.
- Topic migration is a separate concern from event schema versioning.

## Operational requirements

Each active event documents:

- owner and consumers;
- topic and message key;
- delivery and ordering semantics;
- required consumer idempotency key;
- data classification;
- retry and DLQ owner;
- produced/consumed metrics;
- compatibility and retirement policy;
- related ADR and runbook.
