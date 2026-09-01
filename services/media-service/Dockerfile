# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv

FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS builder

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_NO_DEV=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock README.md ./
COPY libs ./libs
COPY services ./services
RUN uv sync --locked --no-dev --no-editable --package media-service

FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PATH=/app/.venv/bin:$PATH
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY services/media-service/src ./src
COPY services/media-service/migrations ./migrations
COPY services/media-service/alembic.ini ./alembic.ini
COPY libs/platform-auth/src/platform_auth ./src/platform_auth
# Runtime packages are supplied by the copied uv environment. Remove pip and
# its vendored libraries from the pinned base image; they are not needed here.
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip /usr/local/lib/python3.14/site-packages/pip-*.dist-info /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14 \
    && useradd --create-home --uid 10001 appuser

USER appuser
EXPOSE 8000
CMD ["uvicorn", "media_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
