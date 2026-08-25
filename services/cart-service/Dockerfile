FROM python:3.12.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app

COPY services/cart-service/src ./src
COPY libs/platform-auth/src/platform_auth ./src/platform_auth
RUN pip install --no-cache-dir --disable-pip-version-check \
    "alembic==1.19.1" "asyncpg==0.31.0" "fastapi==0.141.1" \
    "PyJWT[crypto]==2.13.0" "pydantic-settings==2.15.0" "redis==8.1.0" \
    "SQLAlchemy[asyncio]==2.0.52" "uvicorn[standard]==0.52.3"
RUN useradd --create-home --uid 10001 appuser

USER appuser
EXPOSE 8000
CMD ["uvicorn", "cart_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
