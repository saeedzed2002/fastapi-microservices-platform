# Infrastructure

Infrastructure is introduced incrementally and remains separate from application business logic.

Planned concerns include:

- `compose/` and root `docker-compose.yml` for Phase 1 local development;
- PostgreSQL, Kafka, RabbitMQ, Redis, and MinIO configuration;
- OpenTelemetry, Prometheus, Grafana, Loki, and Tempo configuration;
- raw Kubernetes resources in Phase 9;
- Helm charts only after those resources stabilize in Phase 10;
- controlled migration Jobs and network policies.

Phase 9 adds executable raw Kubernetes resources under `kubernetes/`. They are
applied in controlled foundation, migration, and workload stages; see
`docs/runbooks/kubernetes-deployment.md`. The manifests intentionally contain
no runtime credentials, no mutable image tags, and no guessed production
ingress or egress topology.

Application code consumes protocols and environment configuration and must not assume infrastructure is local, in-cluster, single-node, or self-hosted. Production may use managed/external stateful services.
