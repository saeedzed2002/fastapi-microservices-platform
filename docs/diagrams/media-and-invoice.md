# Media and Invoice Flows

## Direct media upload

```mermaid
sequenceDiagram
    actor Client
    participant Media as Media Service
    participant MDB as media_db
    participant Storage as S3-compatible Storage
    participant Dispatcher as Media Task Dispatcher
    participant Rabbit as RabbitMQ
    participant Worker as Media Celery Worker
    participant Kafka

    Client->>Media: request authorized upload
    Media->>MDB: create PENDING metadata
    Media-->>Client: presigned upload URL
    Client->>Storage: direct upload
    Client->>Media: report completion
    Media->>Storage: HEAD / verify object metadata
    Media->>MDB: transaction: UPLOADED + durable task intent
    Dispatcher->>MDB: claim pending task intent
    Dispatcher->>Rabbit: publish processing task
    Rabbit-->>Dispatcher: publisher confirm
    Dispatcher->>MDB: mark task intent dispatched
    Rabbit->>Worker: process media
    Worker->>Storage: read original / write derivatives
    Worker->>MDB: transaction: READY or FAILED + outbox when READY
    MDB-->>Kafka: outbox publisher: media.ready.v1
```

## Generated invoice

```mermaid
sequenceDiagram
    participant Kafka
    participant Order as Order Service
    participant ODB as order_db
    participant Dispatcher as Order Task Dispatcher
    participant Rabbit as RabbitMQ
    participant Worker as Order Invoice Worker
    participant Storage as S3-compatible Storage
    participant Notification as Notification Service
    participant NDB as notification_db
    participant NDispatcher as Notification Task Dispatcher
    participant NWorker as Notification Celery Worker
    participant Provider as Email or SMS Provider

    Kafka->>Order: order.confirmed.v1
    Order->>ODB: transaction: inbox + durable invoice task intent
    Dispatcher->>ODB: claim pending task intent
    Dispatcher->>Rabbit: publish generate-invoice task
    Rabbit-->>Dispatcher: publisher confirm
    Dispatcher->>ODB: mark task intent dispatched
    Rabbit->>Worker: generate invoice
    Worker->>ODB: load immutable order snapshot
    Worker->>Storage: upload PDF
    Worker->>ODB: invoice metadata + outbox
    ODB-->>Kafka: invoice.generated.v1
    Kafka->>Notification: invoice.generated.v1
    Notification->>NDB: transaction: inbox + durable delivery intent
    NDispatcher->>NDB: claim pending delivery intent
    NDispatcher->>Rabbit: publish delivery task
    Rabbit-->>NDispatcher: publisher confirm
    NDispatcher->>NDB: mark delivery intent dispatched
    Rabbit->>NWorker: execute delivery idempotently
    NWorker->>Provider: send with provider idempotency where available
    NWorker->>NDB: persist terminal or retryable delivery result
```

The dispatcher is a bounded-context component, not an in-memory continuation of the HTTP or Kafka handler. The exact claiming, confirmation, retry, and recovery protocol must be decided and validated in the first phase that introduces a critical Kafka-to-RabbitMQ flow; invoice-specific behavior is completed in Phase 6.
