import asyncio
import io
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Query
from jsonschema import Draft202012Validator
from starlette.responses import Response

from platform_observability import configure_application, metrics_response, run_background_process
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


def test_http_errors_use_the_canonical_contract_and_preserve_context_headers() -> None:
    app = FastAPI()
    configure_application(
        app,
        service_name="error-contract-test-service",
        service_version="0.1.0",
        environment="test",
    )

    @app.get("/api/v1/callback")
    async def callback(track_id: str = Query(alias="trackId", min_length=1)) -> dict[str, str]:
        return {"track_id": track_id}

    @app.get("/api/v1/rejected")
    async def rejected() -> None:
        raise HTTPException(status_code=409, detail="internal implementation detail")

    async def request() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            validation_response = await client.get(
                "/api/v1/callback", headers={"x-request-id": "request-123"}
            )
            rejected_response = await client.get("/api/v1/rejected")
            missing_route_response = await client.get("/api/v1/missing")
        return validation_response, rejected_response, missing_route_response

    validation_response, rejected_response, missing_route_response = asyncio.run(request())
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "openapi"
        / "error-response.v1.schema.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))

    assert validation_response.status_code == 422
    assert validation_response.headers["x-request-id"] == "request-123"
    assert validation_response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "Request validation failed.",
        "details": {
            "violations": [
                {
                    "location": ["query", "trackId"],
                    "code": "missing",
                    "message": "Field required",
                }
            ]
        },
        "request_id": "request-123",
    }

    for response, expected_status, expected_code in (
        (validation_response, 422, "VALIDATION_ERROR"),
        (rejected_response, 409, "CONFLICT"),
        (missing_route_response, 404, "RESOURCE_NOT_FOUND"),
    ):
        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code
        assert not list(validator.iter_errors(response.json()))


def test_background_process_stops_workers_and_runs_service_cleanup() -> None:
    cleanup_calls: list[str] = []

    async def worker(stop: asyncio.Event) -> None:
        stop.set()
        await stop.wait()

    async def cleanup() -> None:
        cleanup_calls.append("complete")

    asyncio.run(
        run_background_process(
            service_name="background-process-test-service",
            service_version="0.1.0",
            environment="test",
            workers=(worker,),
            shutdown=cleanup,
        )
    )

    assert cleanup_calls == ["complete"]


def test_background_process_fails_when_a_worker_exits_unexpectedly() -> None:
    cleanup_calls: list[str] = []

    async def worker(_stop: asyncio.Event) -> None:
        return None

    async def cleanup() -> None:
        cleanup_calls.append("complete")

    with pytest.raises(RuntimeError, match="background worker exited unexpectedly"):
        asyncio.run(
            run_background_process(
                service_name="background-process-failure-test-service",
                service_version="0.1.0",
                environment="test",
                workers=(worker,),
                shutdown=cleanup,
            )
        )

    assert cleanup_calls == ["complete"]


def test_background_process_rejects_a_misconfigured_empty_worker_set() -> None:
    async def cleanup() -> None:
        raise AssertionError("cleanup must not run before a worker process starts")

    with pytest.raises(ValueError, match="at least one enabled worker"):
        asyncio.run(
            run_background_process(
                service_name="empty-background-process-test-service",
                service_version="0.1.0",
                environment="test",
                workers=(),
                shutdown=cleanup,
            )
        )
