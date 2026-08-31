from celery import Celery  # type: ignore[import-untyped]

from order_service.config import get_settings
from platform_observability import configure_runtime

settings = get_settings()
configure_runtime(
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
)
celery_app = Celery(
    "order_service",
    broker=settings.rabbitmq_url,
    include=["order_service.workers.invoice_tasks"],
)
celery_app.conf.update(
    imports=("order_service.workers.invoice_tasks",),
    task_default_queue="order.invoice",
    task_serializer="json",
    accept_content=("json",),
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=120,
    task_soft_time_limit=90,
    task_publish_retry=True,
    broker_transport_options={"confirm_publish": True},
    worker_prefetch_multiplier=1,
    worker_enable_remote_control=False,
)
