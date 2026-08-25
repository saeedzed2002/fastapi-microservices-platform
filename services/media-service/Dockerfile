FROM python:3.14.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY libs/platform-auth /app/libs/platform-auth
COPY services/media-service /app/services/media-service
RUN pip install --no-cache-dir /app/libs/platform-auth /app/services/media-service
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app/services/media-service
USER appuser
CMD ["uvicorn", "media_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
