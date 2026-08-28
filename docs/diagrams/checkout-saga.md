# Checkout Saga

```mermaid
sequenceDiagram
    actor Client
    participant Order as Order Service
    participant ODB as order_db
    participant Kafka
    participant Inventory as Inventory Service
    participant IDB as inventory_db
    participant Payment as Payment Service
    participant PDB as payment_db

    Client->>Order: POST /api/v1/orders + Idempotency-Key
    Order->>ODB: transaction: immutable snapshot + PENDING + outbox
    Order-->>Client: accepted / PENDING
    ODB-->>Kafka: outbox publisher: order.created.v1

    Kafka->>Inventory: order.created.v1
    Inventory->>IDB: inbox + atomic reservation + outbox

    alt inventory available
        IDB-->>Kafka: inventory.reserved.v1
        Kafka->>Order: inventory.reserved.v1
        Order->>ODB: inbox + persist reservation result + guarded state transition
        Note over Order,ODB: Phase 5 defines the durable trigger for PAYMENT_PENDING
        Kafka->>Payment: inventory.reserved.v1
        Payment->>PDB: inbox + AWAITING_CUSTOMER + payment.processing.v1 outbox
        Client->>Payment: authenticated payment start
        Payment->>Order: authenticated ownership and PAYMENT_PENDING REST check
        Payment->>PDB: commit REQUESTING attempt
        Payment->>Payment: Zarinpal request outside transaction
        Payment->>PDB: authority + PENDING_CUSTOMER
        Client->>Payment: Zarinpal browser return
        Payment->>Payment: verify persisted authority with Zarinpal

        alt payment succeeds
            PDB-->>Kafka: payment.succeeded.v1
            Kafka->>Order: payment.succeeded.v1
            Order->>ODB: inbox + guarded transition to CONFIRMED + outbox
            ODB-->>Kafka: outbox publisher: order.confirmed.v1
        else payment fails
            PDB-->>Kafka: payment.failed.v1
            Kafka->>Order: payment.failed.v1
            Order->>ODB: inbox + guarded transition to CANCELLED + outbox
            Kafka->>Inventory: payment.failed.v1 compensation trigger
            Inventory->>IDB: inbox + release reservation once + outbox
        end
    else inventory unavailable
        IDB-->>Kafka: inventory.reservation_failed.v1
        Kafka->>Order: inventory.reservation_failed.v1
        Order->>ODB: inbox + PENDING to CANCELLED + outbox
    end
```

`PENDING`, `INVENTORY_RESERVED`, `PAYMENT_PENDING`, `CONFIRMED`, `CANCELLED`, and `FAILED` form the minimum explicit order-state vocabulary. The diagram deliberately does not collapse `INVENTORY_RESERVED` and `PAYMENT_PENDING` into one database transaction: Phase 5 must define the durable observation or contract that triggers the latter. `FAILED` is reserved for a Phase 5-defined terminal failure that is not represented by normal business cancellation. The complete transition table, guards, history requirements, and emitted events are Phase 5 deliverables.

Kafka ordering is only partition-local. There is no ordering guarantee between inventory and payment topics or between different aggregate keys. The Order consumer must therefore combine Inbox deduplication, conditional state transitions, and a Phase 5-defined retry/reconciliation policy so that an out-of-order payment event cannot force an illegal transition.

ADR-022 fixes the Zarinpal start, verification, expiry, unknown-request, and
late-success policies. The provider request happens after a durable
`REQUESTING` marker and outside the Payment transaction. Expiry writes
`payment.failed.v1` through the normal Payment outbox, and a late verified
success is recorded for manual refund without resurrecting the Order. Refund
execution remains outside the current scope.
