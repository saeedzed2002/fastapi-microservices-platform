# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv

FROM python:3.14.7-slim-bookworm@sha256:416f0db2a2b561945630cef9877a7ea0581b27449eb9fd9df42f03e1b74b5b63 AS builder

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_NO_DEV=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_HTTP_TIMEOUT=180 UV_HTTP_RETRIES=5

COPY pyproject.toml uv.lock README.md ./
COPY libs ./libs
COPY services ./services
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package shipping-service

FROM python:3.14.7-slim-bookworm@sha256:416f0db2a2b561945630cef9877a7ea0581b27449eb9fd9df42f03e1b74b5b63

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PATH=/app/.venv/bin:$PATH
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY services/shipping-service/src ./src
COPY services/shipping-service/migrations ./migrations
COPY services/shipping-service/alembic.ini ./alembic.ini
# Runtime packages are supplied by the copied uv environment. Remove pip and
# its vendored libraries from the pinned base image; they are not needed here.
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip /usr/local/lib/python3.14/site-packages/pip-*.dist-info /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14 \
    && useradd --create-home --uid 10001 appuser

USER appuser
EXPOSE 8000
CMD ["uvicorn", "shipping_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
