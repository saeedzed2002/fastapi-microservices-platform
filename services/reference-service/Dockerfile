FROM python:3.14.7-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY services/reference-service/pyproject.toml ./
COPY services/reference-service/src ./src

RUN pip install --no-cache-dir --disable-pip-version-check \
    "fastapi==0.141.1" "pydantic-settings==2.15.0" "uvicorn[standard]==0.52.3"

USER 10001
EXPOSE 8000
CMD ["uvicorn", "reference_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
