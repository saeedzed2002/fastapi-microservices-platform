from celery import Celery  # type: ignore[import-untyped]

from notification_service.config import get_settings

settings = get_settings()
celery_app = Celery(
    "notification_service",
    broker=settings.rabbitmq_url,
    include=["notification_service.workers.email_tasks", "notification_service.workers.sms_tasks"],
)
celery_app.conf.update(
    imports=("notification_service.workers.email_tasks", "notification_service.workers.sms_tasks"),
    task_default_queue="notification.email",
    task_serializer="json",
    accept_content=("json",),
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=60,
    task_soft_time_limit=45,
    task_publish_retry=True,
    broker_transport_options={"confirm_publish": True},
    worker_prefetch_multiplier=1,
    worker_enable_remote_control=False,
)
