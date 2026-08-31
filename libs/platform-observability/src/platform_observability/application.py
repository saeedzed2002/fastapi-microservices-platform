"""FastAPI integration for context, metrics, JSON logs, and OTLP traces."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_observability.context import (
    inject_trace_context,
    new_request_context,
    reset_request_context,
    set_request_context,
)
from platform_observability.logging import (
    configure_logging,
    otlp_endpoint,
    shutdown_logging,
    telemetry_is_enabled,
)
from platform_observability.metrics import record_http_request

_tracer_provider: TracerProvider | None = None
logger = logging.getLogger("platform-observability.http")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        self.app = app
        self.service_name = service_name
        self.tracer = trace.get_tracer("platform-observability.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        request_context = new_request_context(headers)
        context_token = set_request_context(request_context)
        state = scope.setdefault("state", {})
        state.update(
            {
                "request_id": request_context.request_id,
                "correlation_id": request_context.correlation_id,
                "causation_id": request_context.causation_id,
            }
        )
        status_code = 500
        started_at = time.perf_counter()

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"x-request-id", b"x-correlation-id", b"traceparent"}
                ]
                trace_headers = inject_trace_context()
                response_headers.extend(
                    [
                        (b"x-request-id", request_context.request_id.encode()),
                        (b"x-correlation-id", request_context.correlation_id.encode()),
                    ]
                )
                if "traceparent" in trace_headers:
                    response_headers.append((b"traceparent", trace_headers["traceparent"].encode()))
                message["headers"] = response_headers
            await send(message)

        parent_context = propagate.extract(headers)
        try:
            with self.tracer.start_as_current_span(
                "http.server.request", context=parent_context, kind=SpanKind.SERVER
            ) as span:
                try:
                    span.set_attribute("http.request.method", scope["method"])
                    await self.app(scope, receive, send_with_context)
                except Exception:
                    span.set_status(Status(StatusCode.ERROR))
                    raise
                finally:
                    route = getattr(scope.get("route"), "path", "unmatched")
                    span.set_attribute("http.route", route)
                    span.set_attribute("http.response.status_code", status_code)
                    if status_code >= 500:
                        span.set_status(Status(StatusCode.ERROR))
                    record_http_request(
                        service=self.service_name,
                        method=scope["method"],
                        route=route,
                        status=status_code,
                        duration_seconds=time.perf_counter() - started_at,
                    )
                    logger.info("http_request_completed")
        finally:
            reset_request_context(context_token)


def configure_application(
    app: FastAPI,
    *,
    service_name: str,
    service_version: str,
    environment: str,
    log_level: str = "INFO",
) -> None:
    configure_runtime(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        log_level=log_level,
    )
    app.add_middleware(RequestContextMiddleware, service_name=service_name)
    app.router.add_event_handler("shutdown", shutdown_runtime)


def configure_runtime(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    log_level: str = "INFO",
) -> None:
    global _tracer_provider
    enabled = telemetry_is_enabled()
    endpoint = otlp_endpoint()
    if _tracer_provider is None:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.version": service_version,
                    "deployment.environment.name": environment,
                }
            )
        )
        if enabled:
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer_provider = provider
    configure_logging(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        level=log_level,
        otlp_enabled=enabled,
        otlp_endpoint=endpoint,
    )


def shutdown_runtime() -> None:
    try:
        if _tracer_provider is not None:
            _tracer_provider.force_flush(timeout_millis=5_000)
            _tracer_provider.shutdown()
    finally:
        shutdown_logging()
