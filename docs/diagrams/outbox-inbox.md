# Transactional Outbox and Inbox

```mermaid
flowchart LR
    request[Command / consumed event]

    subgraph producer[Producer local transaction]
        state[Business state]
        outbox[Outbox: immutable event data + mutable delivery metadata]
    end

    publisher[Outbox publisher]
    kafka[(Kafka)]

    subgraph consumer[Consumer local transaction]
        inbox[Unique Inbox row]
        effect[Conditional business effect]
        next[Resulting Outbox row]
    end

    request --> state
    request --> outbox
    outbox -->|read pending immutable record| publisher
    publisher -->|publish| kafka
    kafka -->|broker acknowledgement| publisher
    publisher -->|conditionally set published_at| outbox
    kafka --> inbox
    inbox -->|new event| effect
    inbox -->|duplicate event| ignored[No repeated effect]
    effect --> next
    next --> nextPublisher[Next outbox publisher]
```

Business state and the Outbox row are written together. The event identity, type, key, headers, and payload in that row are immutable; delivery metadata such as claim state, attempts, last error, and `published_at` may change. The publisher reads only the Outbox record and never reconstructs an event from current business tables. If Kafka is unavailable after commit, the row remains pending. If publication succeeds and the publisher crashes before marking success, Kafka may receive a duplicate; the Inbox and domain guards make that safe.
