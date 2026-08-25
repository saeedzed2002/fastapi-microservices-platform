# Deployment Evolution

## Local development — Phase 1

```mermaid
flowchart TB
    developer[Developer]
    services[Local service processes / containers]

    subgraph compose[Docker Compose infrastructure]
        postgres[(PostgreSQL)]
        kafka[(Kafka)]
        rabbit[(RabbitMQ)]
        redis[(Redis)]
        minio[(MinIO)]
        observability[Optional observability profile]
    end

    developer --> services
    services --> postgres
    services --> kafka
    services --> rabbit
    services --> redis
    services --> minio
    services --> observability
```

## Kubernetes target — Phase 9+

```mermaid
flowchart TB
    ingress[Ingress / Edge]

    subgraph cluster[Kubernetes application workloads]
        apis[Stateless API Deployments]
        consumers[Kafka consumer Deployments]
        workers[Celery worker Deployments]
        migrations[Controlled migration Jobs]
    end

    ingress --> apis

    postgres[(External / managed PostgreSQL)]
    kafka[(External / managed Kafka)]
    rabbit[(External / managed RabbitMQ)]
    redis[(External / managed Redis)]
    storage[(S3-compatible storage)]
    telemetry[Observability backends]

    apis --> postgres
    apis --> kafka
    apis --> redis
    apis --> storage
    consumers --> kafka
    consumers --> postgres
    workers --> rabbit
    workers --> postgres
    workers --> storage
    migrations --> postgres
    cluster --> telemetry
```

Stateful dependencies may run in-cluster for a demo environment, but application code is configured so production can use managed/external services without topology-dependent business logic.
