import asyncio
import json
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

from payment_service.main import app


def test_zibal_callback_validation_uses_the_canonical_error_envelope() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/api/v1/payments/zibal/callback",
                headers={"x-request-id": "payment-callback-validation-123"},
            )

    response = asyncio.run(request())
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "openapi"
        / "error-response.v1.schema.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))

    assert response.status_code == 422
    assert response.headers["x-request-id"] == "payment-callback-validation-123"
    assert response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "Request validation failed.",
        "details": {
            "violations": [
                {
                    "location": ["query", "trackId"],
                    "code": "missing",
                    "message": "Field required",
                }
            ]
        },
        "request_id": "payment-callback-validation-123",
    }
    assert not list(validator.iter_errors(response.json()))
