import asyncio
import io
import json
import logging

import httpx
from fastapi import FastAPI
from starlette.responses import Response

from platform_observability import configure_application, metrics_response
from platform_observability.logging import JsonFormatter


def test_application_propagates_safe_context_and_metrics() -> None:
    app = FastAPI()
    configure_application(
        app,
        service_name="test-service",
        service_version="0.1.0",
        environment="test",
    )

    @app.get("/api/v1/things/{thing_id}")
    async def thing(thing_id: str) -> dict[str, str]:
        return {"thing_id": thing_id}

    @app.get("/metrics")
    async def metrics() -> Response:
        return metrics_response()

    async def request() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/things/never-a-metric-label",
                headers={"x-request-id": "request-123", "x-correlation-id": "workflow-456"},
            )
            metrics_response_value = await client.get("/metrics")
        return response, metrics_response_value

    response, metric_result = asyncio.run(request())

    assert response.headers["x-request-id"] == "request-123"
    assert response.headers["x-correlation-id"] == "workflow-456"
    assert response.headers["traceparent"].startswith("00-")
    assert 'route="/api/v1/things/{thing_id}"' in metric_result.text
    assert "never-a-metric-label" not in metric_result.text


def test_request_completion_log_contains_active_trace_identifier() -> None:
    app = FastAPI()
    configure_application(
        app,
        service_name="trace-log-test-service",
        service_version="0.1.0",
        environment="test",
    )

    @app.get("/api/v1/trace-log")
    async def trace_log() -> dict[str, str]:
        return {"status": "ok"}

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        JsonFormatter(
            service_name="trace-log-test-service",
            service_version="0.1.0",
            environment="test",
        )
    )
    request_logger = logging.getLogger("platform-observability.http")
    request_logger.addHandler(handler)
    try:

        async def request() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get("/api/v1/trace-log")

        response = asyncio.run(request())
    finally:
        request_logger.removeHandler(handler)

    request_trace_id = response.headers["traceparent"].split("-")[1]
    completion_log = next(
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if '"message":"http_request_completed"' in line
    )
    assert completion_log["trace_id"] == request_trace_id
