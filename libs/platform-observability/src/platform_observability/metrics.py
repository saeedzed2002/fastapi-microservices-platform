"""Low-cardinality Prometheus metrics owned by the technical platform layer."""

import logging

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter(
    "platform_http_requests_total",
    "Completed HTTP requests.",
    ("service", "method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "platform_http_request_duration_seconds",
    "Completed HTTP request duration.",
    ("service", "method", "route", "status"),
)
DATABASE_QUERY_DURATION = Histogram(
    "platform_database_query_duration_seconds",
    "Database query duration by low-cardinality operation and result.",
    ("service", "operation", "outcome"),
)
DATABASE_POOL_CHECKED_OUT = Gauge(
    "platform_database_pool_checked_out",
    "Database connections currently checked out from a pool.",
    ("service",),
)
DATABASE_POOL_SIZE = Gauge(
    "platform_database_pool_size",
    "Configured database connection pool size when the pool exposes it.",
    ("service",),
)
KAFKA_RECORDS = Counter(
    "platform_kafka_records_total",
    "Kafka records processed by outcome.",
    ("service", "consumer", "outcome"),
)
KAFKA_DLQ_RECORDS = Counter(
    "platform_kafka_dead_letter_records_total",
    "Kafka records durably written to the dead-letter topic.",
    ("service", "consumer"),
)


def metrics_response(*, extra: str = "") -> Response:
    content = generate_latest()
    if extra:
        content += extra.encode()
    return Response(content=content, media_type=CONTENT_TYPE_LATEST)


def record_http_request(
    *,
    service: str,
    method: str,
    route: str,
    status: int,
    duration_seconds: float,
) -> None:
    """Record completed HTTP telemetry without altering request behavior."""

    try:
        labels = {"service": service, "method": method, "route": route, "status": str(status)}
        HTTP_REQUESTS.labels(**labels).inc()
        HTTP_REQUEST_DURATION.labels(**labels).observe(duration_seconds)
    except Exception:
        logger.exception("observability_http_metric_recording_failed")


def record_database_query(
    *, service: str, operation: str, outcome: str, duration_seconds: float
) -> None:
    """Record query telemetry without interrupting database work."""

    try:
        DATABASE_QUERY_DURATION.labels(
            service=service,
            operation=operation,
            outcome=outcome,
        ).observe(duration_seconds)
    except Exception:
        logger.exception("observability_database_metric_recording_failed")


def update_database_pool(
    *, service: str, pool_size: float | None, checked_out: float | None
) -> None:
    """Update pool gauges without allowing telemetry to affect pool events."""

    try:
        if pool_size is not None:
            DATABASE_POOL_SIZE.labels(service=service).set(pool_size)
        if checked_out is not None:
            DATABASE_POOL_CHECKED_OUT.labels(service=service).set(checked_out)
    except Exception:
        logger.exception("observability_database_pool_metric_recording_failed")


def record_kafka_record(*, service: str, consumer: str, outcome: str) -> None:
    """Record a bounded Kafka consumer outcome without affecting delivery."""

    try:
        KAFKA_RECORDS.labels(service=service, consumer=consumer, outcome=outcome).inc()
    except Exception:
        logger.exception("observability_kafka_metric_recording_failed")


def record_kafka_dead_letter(*, service: str, consumer: str) -> None:
    """Record a durable DLQ outcome without affecting the consumer commit path."""

    try:
        KAFKA_DLQ_RECORDS.labels(service=service, consumer=consumer).inc()
    except Exception:
        logger.exception("observability_kafka_dlq_metric_recording_failed")
