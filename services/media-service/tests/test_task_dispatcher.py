import asyncio
from unittest.mock import Mock

import pytest

from media_service.workers import task_dispatcher


def test_dispatch_asset_sends_to_media_processing_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    send_task = Mock()
    monkeypatch.setattr(task_dispatcher.celery_app, "send_task", send_task)

    asyncio.run(
        task_dispatcher._dispatch_asset(
            media_asset_id="e47b10c4-47a7-4c6f-a614-f142a57c6f03",
            timeout_seconds=1.0,
        )
    )

    send_task.assert_called_once_with(
        "media_service.process_asset",
        kwargs={"media_asset_id": "e47b10c4-47a7-4c6f-a614-f142a57c6f03"},
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
            task_dispatcher._dispatch_asset(
                media_asset_id="e47b10c4-47a7-4c6f-a614-f142a57c6f03",
                timeout_seconds=0.01,
            )
        )
