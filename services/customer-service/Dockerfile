FROM python:3.14.7-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY services/customer-service/src ./src
COPY services/customer-service/pyproject.toml ./
COPY libs/platform-auth/src/platform_auth ./src/platform_auth

RUN pip install --no-cache-dir --disable-pip-version-check \
    "aiokafka==0.14.0" "alembic==1.19.1" "asyncpg==0.31.0" \
    "fastapi==0.141.1" "PyJWT[crypto]==2.13.0" "pydantic-settings==2.15.0" \
    "SQLAlchemy[asyncio]==2.0.52" "uvicorn[standard]==0.52.3"

USER 10001
EXPOSE 8000
CMD ["uvicorn", "customer_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
