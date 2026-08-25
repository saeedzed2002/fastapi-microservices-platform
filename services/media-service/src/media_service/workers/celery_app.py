from celery import Celery  # type: ignore[import-untyped]

from media_service.config import get_settings

settings = get_settings()
celery_app = Celery(
    "media_service",
    broker=settings.rabbitmq_url,
    include=["media_service.workers.tasks"],
)
celery_app.conf.update(
    imports=("media_service.workers.tasks",),
    task_default_queue="media.processing",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=120,
    task_soft_time_limit=90,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_enable_remote_control=False,
)
