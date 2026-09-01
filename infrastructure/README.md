# Infrastructure

Infrastructure remains separate from application business logic. The current
delivery assets provide:

- local Compose topology in `compose/docker-compose.yml`, selected by the
  ignored root `.env` through `COMPOSE_FILE`;
- PostgreSQL, Kafka, RabbitMQ, Redis, and MinIO configuration;
- opt-in OpenTelemetry, Prometheus, Grafana, Loki, and Tempo observability;
- raw Kubernetes resources, controlled migration Jobs, network policies, and
  disposable `Kind` conformance; and
- Helm charts that package the reviewed foundation and application-release
  sequence.

Phase 9 adds executable raw Kubernetes resources under `kubernetes/`. They are
applied in controlled foundation, migration, and workload stages; see
`docs/runbooks/kubernetes-deployment.md`. The manifests intentionally contain
no runtime credentials, no mutable image tags, and no guessed production
ingress or egress topology.

Application code consumes protocols and environment configuration and must not assume infrastructure is local, in-cluster, single-node, or self-hosted. Production may use managed/external stateful services.
