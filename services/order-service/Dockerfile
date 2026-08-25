FROM python:3.14.6-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY services/order-service/src ./src
COPY libs/platform-auth/src/platform_auth ./src/platform_auth
RUN pip install --no-cache-dir --disable-pip-version-check "aiokafka==0.14.0" "alembic==1.19.1" "asyncpg==0.31.0" "boto3==1.43.79" "celery==5.6.3" "fastapi==0.141.1" "httpx==0.28.1" "PyJWT[crypto]==2.13.0" "pydantic-settings==2.15.0" "reportlab==5.0.1" "SQLAlchemy[asyncio]==2.0.52" "uvicorn[standard]==0.52.3"
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "order_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
