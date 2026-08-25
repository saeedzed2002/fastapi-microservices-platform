# Realtime Chat

```mermaid
sequenceDiagram
    actor UserA as User A
    participant Media as Media Service
    participant PodA as Chat Pod A
    participant DB as chat_db
    participant Redis
    participant PodB as Chat Pod B
    actor UserB as User B

    opt attachment already uploaded through Media flow
        UserA->>Media: obtain ready authorized media asset ID
        UserA->>PodA: authenticated WebSocket message + media asset ID
        PodA->>Media: validate ownership and readiness before DB transaction
        Media-->>PodA: authorized attachment metadata
    end
    UserA->>PodA: authenticated WebSocket message or attachment-free content
    PodA->>PodA: validate membership and payload
    PodA->>DB: commit Message + MessageAttachment associations
    DB-->>PodA: committed
    PodA-->>UserA: durable ACK
    PodA->>Redis: publish committed message notification
    Redis->>PodB: fan-out notification
    PodB-->>UserB: realtime message

    Note over DB,Redis: PostgreSQL is durable truth; Redis is ephemeral delivery.
```

When Redis is unavailable, the committed message remains in PostgreSQL. Reconnecting clients retrieve missed history by stable cursor/message ID and deduplicate any repeated frames. Chat stores only the durable association to an authorized Media asset; object bytes and upload/processing lifecycle remain owned by Media Service.
