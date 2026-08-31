import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response

from platform_observability import configure_application, metrics_response
from reference_service.config import get_settings

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("service_started")
    yield
    logger.info("service_stopped")


app = FastAPI(title="Reference Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
    log_level=settings.log_level,
)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()


@app.get("/api/v1/reference", tags=["reference"])
async def reference(request: Request) -> dict[str, Any]:
    state = request.scope.get("state", {})
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "environment": settings.environment,
        "request_id": state.get("request_id"),
        "correlation_id": state.get("correlation_id"),
    }
