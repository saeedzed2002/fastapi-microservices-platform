import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx

from payment_service.application import reverse_zarinpal_payment
from payment_service.models import OutboxMessage, PaymentReversal
from payment_service.zarinpal import ZarinpalClient


def test_reverse_persists_the_request_before_calling_zarinpal() -> None:
    async def exercise() -> None:
        intent = SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            method="zarinpal",
            status="SUCCEEDED",
            provider_reference="zarinpal:123456",
        )
        attempt = SimpleNamespace(
            id=uuid4(),
            intent_id=intent.id,
            provider="zarinpal",
            status="SUCCEEDED",
            authority="S000000000",
        )
        added: list[object] = []
        commit = AsyncMock()

        def add(row: object) -> None:
            if isinstance(row, PaymentReversal):
                row.id = uuid4()
            added.append(row)

        scalar_call = 0

        async def scalar(_: object) -> object | None:
            nonlocal scalar_call
            scalar_call += 1
            if scalar_call == 1:
                return intent
            if scalar_call == 2:
                return None
            if scalar_call == 3:
                return attempt
            if scalar_call == 4:
                return intent
            return next(row for row in added if isinstance(row, PaymentReversal))

        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=scalar),
            add=Mock(side_effect=add),
            commit=commit,
        )

        async def handler(request: httpx.Request) -> httpx.Response:
            assert commit.await_count == 1
            assert request.url.path == "/pg/v4/payment/reverse.json"
            assert json.loads(request.content)["authority"] == attempt.authority
            return httpx.Response(200, json={"data": {"code": 100}})

        client = ZarinpalClient(
            merchant_id="00000000-0000-0000-0000-000000000000",
            sandbox=True,
            callback_url="https://localhost/api/v1/payments/zarinpal/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )
        refund_request_id = uuid4()
        requested_by = uuid4()

        result = await reverse_zarinpal_payment(
            db,
            order_id=intent.order_id,
            requested_by=requested_by,
            idempotency_key=f"refund-request:{refund_request_id}",
            refund_request_id=refund_request_id,
            provider=client,
        )

        reversal = next(row for row in added if isinstance(row, PaymentReversal))
        assert result.reversal_id == reversal.id
        assert result.payment_status == "refunded"
        assert intent.status == "REFUNDED"
        assert reversal.status == "SUCCEEDED"
        assert reversal.requested_by == requested_by
        assert commit.await_count == 2
        events = [row for row in added if isinstance(row, OutboxMessage)]
        assert len(events) == 1
        assert events[0].event_type == "payment.refunded.v1"
        assert events[0].payload["refund_request_id"] == str(refund_request_id)

    asyncio.run(exercise())
