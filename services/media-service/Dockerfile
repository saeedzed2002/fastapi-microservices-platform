# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv

FROM python:3.14.7-slim-bookworm@sha256:416f0db2a2b561945630cef9877a7ea0581b27449eb9fd9df42f03e1b74b5b63 AS builder

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_NO_DEV=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock README.md ./
COPY libs ./libs
COPY services ./services
RUN uv sync --locked --no-dev --no-editable --package media-service

FROM python:3.14.7-slim-bookworm@sha256:416f0db2a2b561945630cef9877a7ea0581b27449eb9fd9df42f03e1b74b5b63

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PATH=/app/.venv/bin:$PATH
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY services/media-service/src ./src
COPY services/media-service/migrations ./migrations
COPY services/media-service/alembic.ini ./alembic.ini
COPY libs/platform-auth/src/platform_auth ./src/platform_auth
RUN useradd --create-home --uid 10001 appuser

USER appuser
EXPOSE 8000
CMD ["uvicorn", "media_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
