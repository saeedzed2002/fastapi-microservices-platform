import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.application import (
    _has_successful_zarinpal_attempt,
    process_zarinpal_refund_request,
    reverse_zarinpal_payment,
)
from payment_service.models import InboxMessage, OutboxMessage, PaymentReversal
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

        db = cast(
            AsyncSession,
            SimpleNamespace(
                scalar=AsyncMock(side_effect=scalar),
                add=Mock(side_effect=add),
                commit=commit,
            ),
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
        return_request_id = uuid4()
        requested_by = uuid4()

        result = await reverse_zarinpal_payment(
            db,
            order_id=intent.order_id,
            requested_by=requested_by,
            idempotency_key=f"refund-request:{refund_request_id}",
            refund_request_id=refund_request_id,
            provider=client,
            return_request_id=return_request_id,
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
        assert events[0].payload["return_request_id"] == str(return_request_id)
        assert reversal.return_request_id == return_request_id

    asyncio.run(exercise())


def test_zibal_success_is_not_sent_to_zarinpal_reversal() -> None:
    async def exercise() -> None:
        intent = SimpleNamespace(id=uuid4(), order_id=uuid4(), method="online", status="SUCCEEDED")
        db = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(side_effect=[intent, None])))

        assert not await _has_successful_zarinpal_attempt(db, order_id=intent.order_id)

    asyncio.run(exercise())


def test_not_ready_refund_commits_inbox_and_failure_fact_together() -> None:
    async def exercise() -> None:
        intent = SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            method="online",
            status="SUCCEEDED",
            provider_reference="zibal:123456",
        )
        event_id = uuid4()
        refund_request_id = uuid4()
        added: list[object] = []
        commit = AsyncMock()

        db = cast(
            AsyncSession,
            SimpleNamespace(
                scalar=AsyncMock(side_effect=[None, intent, None, intent]),
                add=Mock(side_effect=added.append),
                commit=commit,
            ),
        )
        client = ZarinpalClient(
            merchant_id="",
            sandbox=True,
            callback_url="https://localhost/api/v1/payments/zarinpal/callback",
            timeout_seconds=10,
        )

        assert await process_zarinpal_refund_request(
            db,
            {
                "event_id": str(event_id),
                "event_type": "order.refund_requested.v1",
                "payload": {
                    "order_id": str(intent.order_id),
                    "refund_request_id": str(refund_request_id),
                    "requested_by": str(uuid4()),
                },
            },
            provider=client,
        )

        assert commit.await_count == 1
        failure_events = [row for row in added if isinstance(row, OutboxMessage)]
        inbox_rows = [row for row in added if isinstance(row, InboxMessage)]
        assert len(failure_events) == 1
        assert failure_events[0].event_type == "payment.refund_failed.v1"
        assert failure_events[0].causation_id == event_id
        assert len(inbox_rows) == 1
        assert inbox_rows[0].event_id == event_id

    asyncio.run(exercise())


def test_local_test_payment_refund_preserves_return_correlation() -> None:
    async def exercise() -> None:
        intent = SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            method="test_success",
            status="SUCCEEDED",
            provider_reference="fake-test-payment",
        )
        attempt = SimpleNamespace(id=uuid4(), intent_id=intent.id)
        refund_request_id = uuid4()
        return_request_id = uuid4()
        added: list[object] = []

        def add(row: object) -> None:
            if isinstance(row, PaymentReversal):
                row.id = uuid4()
            added.append(row)

        db = cast(
            AsyncSession,
            SimpleNamespace(
                scalar=AsyncMock(side_effect=[None, intent, attempt.id, intent, None, attempt]),
                add=Mock(side_effect=add),
                flush=AsyncMock(),
                commit=AsyncMock(),
            ),
        )
        client = ZarinpalClient(
            merchant_id="",
            sandbox=True,
            callback_url="https://localhost/api/v1/payments/zarinpal/callback",
            timeout_seconds=10,
        )

        assert await process_zarinpal_refund_request(
            db,
            {
                "event_id": str(uuid4()),
                "event_type": "order.refund_requested.v1",
                "payload": {
                    "order_id": str(intent.order_id),
                    "refund_request_id": str(refund_request_id),
                    "requested_by": str(uuid4()),
                    "return_request_id": str(return_request_id),
                },
            },
            provider=client,
            allow_test_refund=True,
        )

        assert intent.status == "REFUNDED"
        events = [row for row in added if isinstance(row, OutboxMessage)]
        assert len(events) == 1
        assert events[0].event_type == "payment.refunded.v1"
        assert events[0].payload["return_request_id"] == str(return_request_id)

    asyncio.run(exercise())
