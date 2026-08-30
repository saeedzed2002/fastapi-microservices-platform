import asyncio
from unittest.mock import Mock
from uuid import uuid4

import pytest

from media_service.models import MediaTaskIntent
from media_service.workers import task_dispatcher


def test_dispatch_process_asset_intent_sends_to_media_processing_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_task = Mock()
    monkeypatch.setattr(task_dispatcher.celery_app, "send_task", send_task)
    asset_id = "e47b10c4-47a7-4c6f-a614-f142a57c6f03"

    asyncio.run(
        task_dispatcher._dispatch_intent(
            MediaTaskIntent(
                id=uuid4(),
                task_name="media.process_asset.v1",
                payload={"media_asset_id": asset_id},
            ),
            timeout_seconds=1.0,
        )
    )

    send_task.assert_called_once_with(
        "media_service.process_asset",
        kwargs={"media_asset_id": asset_id},
        queue="media.processing",
    )


def test_dispatch_delete_asset_intent_sends_to_media_processing_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_task = Mock()
    monkeypatch.setattr(task_dispatcher.celery_app, "send_task", send_task)

    asyncio.run(
        task_dispatcher._dispatch_intent(
            MediaTaskIntent(
                id=uuid4(),
                task_name="media.delete_asset.v1",
                payload={"media_asset_id": "f6fa031b-2b0e-4296-8eb0-aae90f44ee23"},
            ),
            timeout_seconds=1.0,
        )
    )

    send_task.assert_called_once_with(
        "media_service.delete_asset",
        kwargs={"media_asset_id": "f6fa031b-2b0e-4296-8eb0-aae90f44ee23"},
        queue="media.processing",
    )


def test_dispatch_asset_times_out_without_blocking_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never_returns(*args: object, **kwargs: object) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(task_dispatcher.asyncio, "to_thread", never_returns)

    with pytest.raises(TimeoutError):
        asyncio.run(
            task_dispatcher._dispatch_intent(
                MediaTaskIntent(
                    id=uuid4(),
                    task_name="media.process_asset.v1",
                    payload={"media_asset_id": "e47b10c4-47a7-4c6f-a614-f142a57c6f03"},
                ),
                timeout_seconds=0.01,
            )
        )
