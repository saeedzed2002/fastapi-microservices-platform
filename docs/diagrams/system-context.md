# System Context

```mermaid
flowchart LR
    web[Future Web Client]
    mobile[Future Mobile Client]
    admin[Future Admin Client]
    third[Third-party Client]

    edge[Edge / API Gateway]
    platform[FastAPI Microservices Platform]

    payment[Payment Provider]
    email[Email Provider]
    sms[SMS Provider]
    object[S3-compatible Object Storage]

    web --> edge
    mobile --> edge
    admin --> edge
    third --> edge
    edge --> platform

    platform <--> payment
    platform --> email
    platform --> sms
    platform <-->|control and metadata verification| object
    web <-->|presigned object data| object
    mobile <-->|presigned object data| object
    admin <-->|presigned object data| object
    third <-->|presigned object data| object
```

The payment-provider relationship is bidirectional because the platform sends provider commands and receives authenticated callbacks/webhooks. The edge handles routing, TLS, request limits, headers, and WebSocket forwarding. Services still validate authentication and enforce domain/resource authorization. Authorized interactive transfers use presigned client-to-storage data paths. Context-owned workers may also read or write object bytes directly through the `ObjectStorage` adapter, while API request handlers retain the authorization/metadata control plane and do not proxy large transfers.
