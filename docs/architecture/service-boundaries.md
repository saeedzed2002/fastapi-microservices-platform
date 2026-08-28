# Service Boundaries

Each service owns its durable state, business invariants, migrations, API, event contracts, tests, deployment artifact, and operational behavior. Cross-service database access and cross-service source imports are forbidden.

## Core services

### Identity Service

Owns accounts, credential hashes, access/refresh-token lifecycle, device/session records, roles, permissions, OTP infrastructure, and authentication security events.

Does not own customer profiles, addresses, preferences, carts, orders, or payment records.

Customers authenticate with phone and OTP; `admin` and `support_agent` staff
authenticate with email and password. Identity owns staff lifecycle, the
normalized phone, code hash, verification attempts, cooldown, rate limits, and
short-lived delivery code in its own Redis namespace. It asks Notification for
directed SMS delivery through an authenticated private API, but never exposes
raw OTP values in Kafka, durable storage, logs, or public responses. It emits
only the post-verification `identity.user_registered.v2` domain fact.

Primary interactions are synchronous authentication APIs, downstream token validation, asynchronous account lifecycle events, and Redis-backed short-lived security state where its failure policy is explicit.

### Customer Service

Owns customer profiles, contact email, addresses, general preferences, and
customer-specific business data. A contact email is not an Identity credential;
it is customer-owned profile data used by a future checkout snapshot.

Does not own credentials, token rotation, authentication roles, orders, or notification delivery attempts.

It exposes authenticated profile/address APIs and may consume Identity lifecycle events. Checkout uses an explicit contract or snapshot; it never reads Customer tables directly.

### Catalog Service

Owns products, variants, categories, brands, attributes, prices, metadata, and product lifecycle.

Does not own stock, reservations, carts, orders, binary files, or the search index as source of truth.

It exposes product/admin APIs, references Media assets through contracts, and emits versioned catalog facts for Search and other projections.

### Inventory Service

Owns SKU stock, `on_hand`, `reserved`, stock movements, reservations, expiration, release, and future warehouse concerns.

Does not own product descriptions/prices, carts, order state, or payment state.

It accepts administrative stock commands and consumes checkout/Saga events. Reservation, release, and adjustment operations must be concurrency-safe, auditable, and idempotent.

### Cart Service

Owns active carts, items, selected variants, quantities, projected totals, and expiration.

Does not own authoritative price, stock reservations, order history, or payment state.

PostgreSQL is authoritative. Redis may cache carts but losing Redis cannot delete them. Cart totals remain projections and are revalidated by the authoritative checkout contract.

### Order Service

Owns checkout acceptance, orders, immutable purchase snapshots, order items, state transitions, platform tracking codes, cancellation, history, Saga participation, and invoice business metadata.

Does not own catalog truth, inventory reservations, provider-facing payment truth, notification delivery, user-upload media lifecycle, or file bytes in PostgreSQL. Order does own the invoice business lifecycle, metadata, and storage key for generated invoices; the bytes live in object storage through its `ObjectStorage` adapter.

It exposes customer-owned checkout/history APIs and a separate read-only
administrator order-review API, writes critical events through an outbox,
consumes Inventory/Payment results, and owns invoice-generation intent after
confirmation.

### Payment Service

Owns payment intents, attempts, provider references, payment status, callbacks/webhooks, refunds, and payment idempotency.

Does not own order state, stock, product data, or customer profiles.

It reacts to the payment stage of the Saga, calls provider adapters, accepts authenticated provider callbacks, and emits payment facts through its outbox.

### Notification Service

Owns notification templates, delivery attempts, delivery status, retries, and channel-specific delivery state.

Does not own order/payment truth, invoice generation, or synchronous checkout behavior.

It consumes domain events, records delivery intent, dispatches RabbitMQ tasks
durably, and executes email/SMS through context-owned Celery workers. For OTP,
it persists provider-facing metadata and a task intent but retrieves the
short-lived code from Identity only immediately before the provider call.

### Media Service

Owns upload authorization, media metadata, presigned URLs, completion verification, processing lifecycle, deletion orchestration, and user-upload object-storage integration.

Does not own product, customer, chat, or invoice business relationships. It does not store binary objects in PostgreSQL.

Clients transfer bytes directly to object storage. Media workers validate and transform files, then publish lifecycle facts such as `media.ready.v1`.

### Chat Service

Owns conversations, participants, messages, durable attachment associations, support-queue assignment, chat authorization, and read/unread state if that feature is introduced.

Does not own identity credentials, binary attachment storage, or durable presence.

It serves HTTP/WebSocket clients, commits messages to PostgreSQL before acknowledgement/fan-out, uses Redis for cross-pod delivery and presence, and references authorized Media assets. Customer-support conversations are queued in Chat PostgreSQL and atomically claimed by one eligible agent, who then becomes the only agent participant. When a participant needs an attachment URL, Chat validates its own membership and requests a short-lived Media URL through a signed internal REST proof; Media continues to own bytes, lifecycle, and URL generation without querying Chat data.

## Later services

### Search Service

Owns a rebuildable, eventually consistent search projection/index. It does not own canonical Catalog data. It consumes versioned Catalog events and serves search queries; replay restores the index after failure.

### Shipping Service

Owns shipments, carrier adapters/references, carrier tracking numbers, shipping status, and fulfilment lifecycle. It does not own the platform order tracking code, payment truth, or inventory truth.

Shipping is intentionally outside the current Phase 0–12 implementation roadmap until a later approved milestone. Order may eventually maintain a customer-facing projection of Shipping facts.

## Boundary enforcement

- Separate service databases, users, grants, and migrations enforce ownership.
- APIs provide synchronous access to current authoritative data.
- Kafka events maintain asynchronous projections and workflows.
- IDs may cross boundaries; ORM/domain objects do not.
- Historical records snapshot required facts instead of depending on mutable foreign data.
- A shared physical development cluster does not grant shared logical ownership.
