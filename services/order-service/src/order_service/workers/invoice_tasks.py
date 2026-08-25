# mypy: disable-error-code=untyped-decorator

import asyncio
import hashlib
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from sqlalchemy import select

from order_service.config import get_settings
from order_service.db import dispose_engine, get_session_factory
from order_service.models import Invoice, Order, OrderItem, OutboxMessage
from order_service.storage import S3ObjectStorage
from order_service.workers.celery_app import celery_app


class InvoiceGenerationInProgress(Exception):
    pass


def render_invoice_pdf(*, order: Order, items: list[OrderItem]) -> bytes:
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=A4, pageCompression=1)
    width, height = A4
    y = height - 56
    pdf.setTitle(f"Invoice {order.tracking_code}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(48, y, "Invoice")
    y -= 30
    pdf.setFont("Helvetica", 10)
    for line in (
        f"Order: {order.tracking_code}",
        f"Customer: {order.customer_email or 'unavailable'}",
        f"Currency: {order.currency}",
        f"Total: {order.total_amount}",
    ):
        pdf.drawString(48, y, line)
        y -= 16
    y -= 12
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(48, y, "Item")
    pdf.drawRightString(width - 48, y, "Amount")
    y -= 16
    pdf.setFont("Helvetica", 10)
    for item in items:
        if y < 72:
            pdf.showPage()
            y = height - 56
        label = f"{item.product_name} ({item.sku}) x {item.quantity}"
        pdf.drawString(48, y, label[:100])
        pdf.drawRightString(width - 48, y, str(item.unit_amount * item.quantity))
        y -= 16
    pdf.save()
    return buffer.getvalue()


async def generate_invoice(
    *, invoice_id: UUID, order_id: UUID, causation_id: UUID, trace_id: str
) -> None:
    settings = get_settings()
    async with get_session_factory()() as db:
        invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
        order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if invoice is None or order is None or invoice.status == "GENERATED":
            return
        now = datetime.now(UTC)
        if (
            invoice.status == "GENERATING"
            and invoice.processing_started_at is not None
            and (now - invoice.processing_started_at).total_seconds()
            < settings.invoice_processing_lease_seconds
        ):
            raise InvoiceGenerationInProgress("invoice generation lease is still active")
        invoice.status = "GENERATING"
        invoice.processing_started_at = now
        invoice.failure_reason = None
        await db.commit()
        items = list(
            await db.scalars(
                select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
            )
        )
    try:
        pdf = render_invoice_pdf(order=order, items=items)
        object_key = f"invoices/{order.id}/invoice.pdf"
        storage = S3ObjectStorage(settings)
        await asyncio.to_thread(storage.ensure_bucket)
        await asyncio.to_thread(
            storage.put_bytes, object_key=object_key, content_type="application/pdf", data=pdf
        )
    except Exception as exc:
        async with get_session_factory()() as db:
            invoice = await db.get(Invoice, invoice_id)
            if invoice is not None and invoice.status != "GENERATED":
                invoice.status = "FAILED"
                invoice.processing_started_at = None
                invoice.failure_reason = str(exc)[:2000]
                await db.commit()
        raise
    async with get_session_factory()() as db:
        invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
        order = await db.get(Order, order_id)
        if invoice is None or order is None or invoice.status == "GENERATED":
            return
        invoice.status = "GENERATED"
        invoice.object_key = object_key
        invoice.checksum_sha256 = hashlib.sha256(pdf).hexdigest()
        invoice.size_bytes = len(pdf)
        invoice.processing_started_at = None
        invoice.generated_at = datetime.now(UTC)
        if order.customer_email:
            db.add(
                OutboxMessage(
                    event_type="invoice.generated.v1",
                    aggregate_type="invoice",
                    aggregate_id=invoice.id,
                    payload={
                        "invoice_id": str(invoice.id),
                        "order_id": str(order.id),
                        "tracking_code": order.tracking_code,
                        "recipient_email": order.customer_email,
                    },
                    correlation_id=order.id,
                    causation_id=causation_id,
                    trace_id=trace_id,
                )
            )
        await db.commit()


async def _generate_and_dispose(**kwargs: object) -> None:
    try:
        await generate_invoice(
            invoice_id=UUID(str(kwargs["invoice_id"])),
            order_id=UUID(str(kwargs["order_id"])),
            causation_id=UUID(str(kwargs["causation_id"])),
            trace_id=str(kwargs["trace_id"]),
        )
    finally:
        await dispose_engine()


@celery_app.task(
    name="order_service.generate_invoice",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 7},
)
def generate_invoice_task(self: object, **kwargs: object) -> None:
    asyncio.run(_generate_and_dispose(**kwargs))
