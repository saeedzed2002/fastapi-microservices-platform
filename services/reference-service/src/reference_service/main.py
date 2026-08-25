import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from reference_service.config import get_settings
from reference_service.observability import RequestContextMiddleware, configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("service_started")
    yield
    logger.info("service_stopped")


app = FastAPI(title="Reference Service", version=settings.service_version, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP reference_service_up Service availability\n"
        "# TYPE reference_service_up gauge\n"
        "reference_service_up 1\n"
    )


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
