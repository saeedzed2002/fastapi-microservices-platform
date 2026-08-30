FROM python:3.14.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app

COPY services/search-service/src ./src
COPY services/search-service/migrations ./migrations
COPY services/search-service/alembic.ini ./alembic.ini
COPY libs/platform-messaging/src/platform_messaging ./src/platform_messaging
RUN pip install --no-cache-dir --disable-pip-version-check \
    "aiokafka==0.14.0" "alembic==1.19.1" "asyncpg==0.31.0" "fastapi==0.141.1" \
    "pydantic-settings==2.15.0" "redis==8.1.0" "SQLAlchemy[asyncio]==2.0.52" \
    "uvicorn[standard]==0.52.3"
RUN useradd --create-home --uid 10001 appuser

USER appuser
EXPOSE 8000
CMD ["uvicorn", "search_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
