# Service Container View

```mermaid
flowchart TB
    clients[Clients] --> edge[Edge / API Gateway]

    subgraph services[FastAPI Microservices]
        identity[Identity]
        customer[Customer]
        catalog[Catalog]
        inventory[Inventory]
        cart[Cart]
        order[Order]
        payment[Payment]
        notification[Notification]
        media[Media]
        chat[Chat]
        search[Search - later]
        shipping[Shipping - later]
    end

    edge --> identity
    edge --> customer
    edge --> catalog
    edge --> inventory
    edge --> cart
    edge --> order
    edge --> payment
    edge --> media
    edge --> chat
    edge --> search

    customer -->|avatar control API| media
    catalog -->|product image control API| media
    chat -->|attachment control API| media

    identity --- identitydb[(identity_db)]
    customer --- customerdb[(customer_db)]
    catalog --- catalogdb[(catalog_db)]
    inventory --- inventorydb[(inventory_db)]
    cart --- cartdb[(cart_db)]
    order --- orderdb[(order_db)]
    payment --- paymentdb[(payment_db)]
    notification --- notificationdb[(notification_db)]
    media --- mediadb[(media_db)]
    chat --- chatdb[(chat_db)]
    search --- searchdb[(search projection)]
    shipping --- shippingdb[(shipping_db)]

    kafka[(Kafka)]
    rabbit[(RabbitMQ)]
    redis[(Redis)]
    objects[(S3-compatible storage)]
    workers[Bounded-context Celery workers]

    identity --> kafka
    kafka --> customer
    catalog <--> kafka
    inventory <--> kafka
    order <--> kafka
    payment <--> kafka
    kafka --> notification
    media <--> kafka
    kafka --> search
    shipping <--> kafka

    notification --> rabbit
    media --> rabbit
    order --> rabbit
    rabbit --> workers

    identity <--> redis
    catalog <--> redis
    cart <--> redis
    chat <--> redis

    clients <-->|presigned object data| objects
    media <--> objects
    workers <--> objects
```

Each database edge denotes exclusive ownership. No horizontal database query exists between services. Media interactions are control-plane calls; authorized clients transfer object bytes directly with narrowly scoped presigned requests.
