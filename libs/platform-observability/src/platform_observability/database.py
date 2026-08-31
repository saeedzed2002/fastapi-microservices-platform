"""Manual SQLAlchemy telemetry without query text or parameter capture."""

from __future__ import annotations

import time
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from platform_observability.metrics import (
    record_database_query,
    update_database_pool,
)

_instrumented_engine_ids: set[int] = set()


def instrument_async_engine(engine: AsyncEngine, *, service_name: str) -> None:
    """Attach one bounded query/pool observer to an async SQLAlchemy engine."""

    instrument_engine(engine.sync_engine, service_name=service_name)


def instrument_engine(sync_engine: Engine, *, service_name: str) -> None:
    """Attach one bounded query/pool observer to a synchronous SQLAlchemy engine."""

    if id(sync_engine) in _instrumented_engine_ids:
        return
    _instrumented_engine_ids.add(id(sync_engine))
    tracer = trace.get_tracer("platform-observability.database")

    def update_pool_metrics(*_: object) -> None:
        try:
            pool = sync_engine.pool
            pool_size = getattr(pool, "size", None)
            checked_out = getattr(pool, "checkedout", None)
            pool_size_value = float(pool_size()) if callable(pool_size) else None
            checked_out_value = float(checked_out()) if callable(checked_out) else None
        except Exception:
            return
        update_database_pool(
            service=service_name,
            pool_size=pool_size_value,
            checked_out=checked_out_value,
        )

    def before_cursor_execute(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        context: Any,
        _executemany: object,
    ) -> None:
        try:
            operation = _statement_operation(statement)
            span = tracer.start_span("db.query", kind=SpanKind.CLIENT)
            span.set_attribute("db.operation.name", operation)
            context._platform_observability_started_at = time.perf_counter()
            context._platform_observability_operation = operation
            context._platform_observability_span = span
        except Exception:
            return

    def after_cursor_execute(
        _connection: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        context: Any,
        _executemany: object,
    ) -> None:
        try:
            _complete_query(context, service_name=service_name, outcome="success")
        except Exception:
            return

    def handle_error(exception_context: object) -> None:
        execution_context = getattr(exception_context, "execution_context", None)
        if execution_context is not None:
            try:
                _complete_query(execution_context, service_name=service_name, outcome="error")
            except Exception:
                return

    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)
    event.listen(sync_engine, "handle_error", handle_error)
    event.listen(sync_engine.pool, "checkout", update_pool_metrics)
    event.listen(sync_engine.pool, "checkin", update_pool_metrics)
    update_pool_metrics()


def _complete_query(context: object, *, service_name: str, outcome: str) -> None:
    started_at = getattr(context, "_platform_observability_started_at", None)
    operation = getattr(context, "_platform_observability_operation", "other")
    span = getattr(context, "_platform_observability_span", None)
    if isinstance(started_at, float):
        record_database_query(
            service=service_name,
            operation=operation,
            outcome=outcome,
            duration_seconds=time.perf_counter() - started_at,
        )
    if span is not None:
        if outcome == "error":
            span.set_status(Status(StatusCode.ERROR))
        span.end()


def _statement_operation(statement: str) -> str:
    first_token = statement.lstrip().split(maxsplit=1)
    if not first_token:
        return "other"
    operation = first_token[0].lower()
    return operation if operation in {"select", "insert", "update", "delete"} else "other"
