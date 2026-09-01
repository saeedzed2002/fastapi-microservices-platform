# End-to-End Tests

The current suite covers these executable cross-service workflows:

- edge TLS routing, security headers, sensitive-route rate limiting, and local
  service Swagger exposure;
- checkout through inventory, payment, confirmation, invoice, notification,
  and the Shipping-to-Order projection;
- public Catalog-to-Search projection, authenticated Chat persistence and
  reconnect recovery, and customer-support assignment;
- durable recovery after Kafka, Redis, and RabbitMQ disruptions; and
- receipt-gated delivered-order returns in the Compose topology.

The suite is deliberately not a claim of exhaustive browser, carrier-provider,
or real-merchant testing. Tests use isolated data, bounded polling of observable
state, and deterministic controls where possible. Fixed sleeps are not a
synchronization strategy.

`test_phase6_checkout_notification.py` is opt-in because it creates isolated
local product, stock, customer, order, invoice, and SMTP test data. Start the
local platform and run it with `RUN_E2E=1`.

The checkout scenario is implemented once in `checkout_workflow.py`. Compose
uses the edge URL through `E2E_BASE_URL`; the disposable Kubernetes conformance
Job supplies individual `E2E_*_BASE_URL` values for the in-cluster
`customer-service`, `catalog-service`, `inventory-service`, and
`order-service` and `shipping-service` `ClusterIP` services. The test therefore remains the same
business workflow in both environments without pretending that the Kind test
exercises public ingress or TLS.

`test_phase18_shipping.py` reuses that checkout evidence, waits for the
Shipping consumer to create its local shipment, exercises an idempotent
administrator transition through the edge, then waits for the Order Kafka
consumer to update the customer-facing projection.

`test_phase19_returns.py` takes a fresh successful test-payment checkout to
the Shipping-owned delivered state, creates and approves one customer return,
records a duplicate-safe physical receipt, and proves that Inventory restores
stock once while the correlated test-payment refund completes. The standalone
test runs in the Compose integration topology. The same portable
`returns_workflow.py` runs in the disposable `Kind` Job after checkout because
that Job sets `E2E_RUN_RETURNS=1`. Neither topology exercises public ingress or
an external payment provider.

`test_phase12_resilience.py` is additionally limited to the disposable Compose
topology because it controls Docker Compose service lifecycle. It never runs
inside the Kind E2E Pod or against a remote environment.
