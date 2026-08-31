"""Structured JSON logging with safe technical correlation fields."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from platform_observability.context import current_context, trace_identifiers

_logger_provider: LoggerProvider | None = None


class JsonFormatter(logging.Formatter):
    """Emit a bounded JSON record without serializing arbitrary log extras."""

    def __init__(self, *, service_name: str, service_version: str, environment: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._service_version = service_version
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        request_context = current_context()
        trace_id, span_id = trace_identifiers()
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "service": self._service_name,
            "service_version": self._service_version,
            "environment": self._environment,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_context is not None:
            payload["request_id"] = request_context.request_id
            payload["correlation_id"] = request_context.correlation_id
            if request_context.causation_id is not None:
                payload["causation_id"] = request_context.causation_id
        if trace_id is not None:
            payload["trace_id"] = trace_id
        if span_id is not None:
            payload["span_id"] = span_id
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class BoundedOtlpLogHandler(LoggingHandler):
    """Export a bounded JSON body while arbitrary ``logging extra`` values stay local."""

    def __init__(self, *, formatter: JsonFormatter, logger_provider: LoggerProvider) -> None:
        super().__init__(level=logging.NOTSET, logger_provider=logger_provider)
        self._json_formatter = formatter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            bounded_record = logging.makeLogRecord(
                {
                    "name": record.name,
                    "levelno": record.levelno,
                    "levelname": record.levelname,
                    "msg": self._json_formatter.format(record),
                    "args": (),
                    "created": record.created,
                }
            )
            super().emit(bounded_record)
        except Exception:
            self.handleError(record)


def configure_logging(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    level: str = "INFO",
    otlp_enabled: bool,
    otlp_endpoint: str,
) -> None:
    global _logger_provider
    formatter = JsonFormatter(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [console_handler]
    if otlp_enabled:
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment.name": environment,
            }
        )
        provider = LoggerProvider(resource=resource)
        provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=otlp_endpoint, insecure=True))
        )
        set_logger_provider(provider)
        _logger_provider = provider
        handlers.append(BoundedOtlpLogHandler(formatter=formatter, logger_provider=provider))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
    logging.captureWarnings(True)


def telemetry_is_enabled() -> bool:
    return os.getenv("PLATFORM_OBSERVABILITY_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def otlp_endpoint() -> str:
    return os.getenv("PLATFORM_OTLP_GRPC_ENDPOINT", "127.0.0.1:4317")


def shutdown_logging() -> None:
    if _logger_provider is not None:
        _logger_provider.force_flush(timeout_millis=5_000)
        _logger_provider.shutdown()
