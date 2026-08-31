"""Request and trace context propagation helpers."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4

from opentelemetry import propagate, trace

_request_context: ContextVar[RequestContext | None] = ContextVar(
    "platform_request_context", default=None
)


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    correlation_id: str
    causation_id: str | None


def new_request_context(headers: Mapping[str, str]) -> RequestContext:
    request_id = _safe_identifier(headers.get("x-request-id")) or uuid4().hex
    correlation_id = _safe_identifier(headers.get("x-correlation-id")) or request_id
    causation_id = _safe_identifier(headers.get("x-causation-id"))
    return RequestContext(
        request_id=request_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


def current_context() -> RequestContext | None:
    return _request_context.get()


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    return _request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _request_context.reset(token)


def inject_trace_context(headers: MutableMapping[str, str] | None = None) -> dict[str, str]:
    carrier: dict[str, str] = {} if headers is None else dict(headers)
    propagate.inject(carrier)
    return carrier


def trace_identifiers() -> tuple[str | None, str | None]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None, None
    return f"{span_context.trace_id:032x}", f"{span_context.span_id:016x}"


def _safe_identifier(value: str | None) -> str | None:
    if value is None or not (1 <= len(value) <= 128):
        return None
    if not all(character.isalnum() or character in "._:-" for character in value):
        return None
    return value
