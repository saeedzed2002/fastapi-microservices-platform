"""FastAPI integration for context, metrics, JSON logs, and OTLP traces."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_observability.context import (
    current_context,
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

BackgroundWorker = Callable[[asyncio.Event], Awaitable[None]]
BackgroundShutdown = Callable[[], Awaitable[None]]

_HTTP_ERROR_CODES = {
    400: ("INVALID_REQUEST", "The request is invalid."),
    401: ("AUTHENTICATION_REQUIRED", "Authentication is required."),
    403: ("FORBIDDEN", "You are not authorized to perform this action."),
    404: ("RESOURCE_NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "The request method is not allowed."),
    409: ("CONFLICT", "The request conflicts with the current resource state."),
    413: ("REQUEST_TOO_LARGE", "The request payload is too large."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "The request media type is not supported."),
    422: ("REQUEST_INVALID", "The request cannot be processed."),
    429: ("RATE_LIMITED", "Too many requests were received."),
    502: ("DEPENDENCY_REJECTED", "A dependent service rejected the request."),
    503: ("DEPENDENCY_UNAVAILABLE", "A required service is unavailable."),
    504: ("DEPENDENCY_TIMEOUT", "A required service did not respond in time."),
}


def _request_id() -> str:
    context = current_context()
    return context.request_id if context is not None else uuid4().hex


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": dict(details or {}),
                "request_id": _request_id(),
            }
        },
        headers=dict(headers) if headers is not None else None,
    )


async def _http_exception_handler(_request: Request, exception: Exception) -> JSONResponse:
    assert isinstance(exception, StarletteHTTPException)
    code, message = _HTTP_ERROR_CODES.get(
        exception.status_code,
        (
            "INTERNAL_SERVER_ERROR" if exception.status_code >= 500 else "HTTP_REQUEST_REJECTED",
            "The service could not complete the request."
            if exception.status_code >= 500
            else "The request was rejected.",
        ),
    )
    return _error_response(
        status_code=exception.status_code,
        code=code,
        message=message,
        headers=exception.headers,
    )


async def _validation_exception_handler(_request: Request, exception: Exception) -> JSONResponse:
    assert isinstance(exception, RequestValidationError)
    violations = [
        {
            "location": [str(part) for part in error["loc"]],
            "code": str(error["type"]),
            "message": str(error["msg"]),
        }
        for error in exception.errors()
    ]
    return _error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        details={"violations": violations},
    )


async def _unhandled_exception_handler(_request: Request, _exception: Exception) -> JSONResponse:
    # Deliberately omit exception text and stack context: these can include raw
    # downstream/provider data and must never be exposed by the HTTP contract.
    logger.error("unhandled_http_exception")
    return _error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="The service could not complete the request.",
    )


def _configure_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    # Router-generated 404/405 errors use Starlette's base HTTP exception,
    # whereas application code normally raises FastAPI's subclass.
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


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
    _configure_error_handlers(app)
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


async def run_background_process(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    workers: Sequence[BackgroundWorker],
    shutdown: BackgroundShutdown,
    log_level: str = "INFO",
) -> None:
    """Run service-owned background loops outside an HTTP application process."""
    if not workers:
        raise ValueError("background process requires at least one enabled worker")
    configure_runtime(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        log_level=log_level,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    registered_signals: list[signal.Signals] = []
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(shutdown_signal, stop.set)
        except NotImplementedError:
            # Signal delivery is available in Linux worker containers. Keeping
            # this fallback also permits direct Windows test invocation.
            continue
        else:
            registered_signals.append(shutdown_signal)

    tasks: list[asyncio.Future[None]] = [asyncio.ensure_future(worker(stop)) for worker in workers]
    stop_task = asyncio.create_task(stop.wait())
    service_logger = logging.getLogger(service_name)
    service_logger.info("background_process_started", extra={"worker_count": len(tasks)})
    try:
        waiters: list[asyncio.Future[Any]] = [stop_task, *tasks]
        done, _ = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        if stop_task not in done:
            for task in done:
                task.result()
            raise RuntimeError("background worker exited unexpectedly")
    finally:
        stop.set()
        stop_task.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(stop_task, *tasks, return_exceptions=True)
        for shutdown_signal in registered_signals:
            loop.remove_signal_handler(shutdown_signal)
        await shutdown()
        shutdown_runtime()
        service_logger.info("background_process_stopped")


def shutdown_runtime() -> None:
    try:
        if _tracer_provider is not None:
            _tracer_provider.force_flush(timeout_millis=5_000)
            _tracer_provider.shutdown()
    finally:
        shutdown_logging()
