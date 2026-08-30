import base64
import json
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from search_service.models import InboxMessage, SearchDocument, SearchTombstone
from search_service.schemas import (
    CatalogProductDeletion,
    CatalogProductProjection,
    SearchProductResponse,
    SearchProductsResponse,
)

_PRODUCT_UPSERT_EVENTS = {"product.created.v1", "product.updated.v1"}
_PRODUCT_DELETE_EVENT = "product.deleted.v1"
_MAX_CURSOR_OFFSET = 10_000


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
        offset = decoded["offset"]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid search cursor"
        ) from exc
    valid_offset = isinstance(offset, int) and not isinstance(offset, bool)
    if not valid_offset or not 0 <= offset <= _MAX_CURSOR_OFFSET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid search cursor"
        )
    return offset


def _response(document: SearchDocument) -> SearchProductResponse:
    if document.published_at is None:
        raise AssertionError("published search result requires published_at")
    return SearchProductResponse(
        product_id=document.product_id,
        slug=document.slug,
        name=document.name,
        description=document.description,
        brand_id=document.brand_id,
        category_id=document.category_id,
        price_amount=document.price_amount,
        currency=document.currency,
        attributes=document.attributes,
        published_at=document.published_at,
    )


async def search_products(
    db: AsyncSession,
    *,
    query: str,
    cursor: str | None,
    limit: int,
    category_id: UUID | None,
    brand_id: UUID | None,
    currency: str | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
) -> SearchProductsResponse:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="min_price cannot exceed max_price",
        )
    offset = decode_cursor(cursor)
    tsquery = func.plainto_tsquery("simple", query)
    rank = func.coalesce(func.ts_rank_cd(SearchDocument.search_vector, tsquery), 0).label("rank")
    matches = SearchDocument.search_vector.op("@@")(tsquery)
    substring_match = or_(
        SearchDocument.name.ilike(f"%{query}%"),
        SearchDocument.slug.ilike(f"%{query}%"),
        SearchDocument.description.ilike(f"%{query}%"),
    )
    conditions = [
        SearchDocument.status == "published",
        SearchDocument.published_at.is_not(None),
        or_(matches, substring_match),
    ]
    if category_id is not None:
        conditions.append(SearchDocument.category_id == category_id)
    if brand_id is not None:
        conditions.append(SearchDocument.brand_id == brand_id)
    if currency is not None:
        conditions.append(SearchDocument.currency == currency.upper())
    if min_price is not None:
        conditions.append(SearchDocument.price_amount >= min_price)
    if max_price is not None:
        conditions.append(SearchDocument.price_amount <= max_price)

    rows = await db.execute(
        select(SearchDocument, rank)
        .where(*conditions)
        .order_by(desc(rank), SearchDocument.source_updated_at.desc(), SearchDocument.product_id)
        .offset(offset)
        .limit(limit + 1)
    )
    documents = [row[0] for row in rows.all()]
    has_next_page = len(documents) > limit
    if has_next_page:
        documents = documents[:limit]
    return SearchProductsResponse(
        items=[_response(document) for document in documents],
        next_cursor=encode_cursor(offset + limit) if has_next_page else None,
    )


async def process_catalog_event(db: AsyncSession, envelope: dict[str, object]) -> bool:
    event_id = UUID(str(envelope["event_id"]))
    event_type = str(envelope["event_type"])
    if await db.scalar(select(InboxMessage.id).where(InboxMessage.event_id == event_id)):
        return False
    db.add(InboxMessage(event_id=event_id, event_type=event_type))
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise ValueError("catalog event payload must be an object")
    if event_type in _PRODUCT_UPSERT_EVENTS:
        await _upsert_document(db, CatalogProductProjection.model_validate(payload))
    elif event_type == _PRODUCT_DELETE_EVENT:
        await _delete_document(db, CatalogProductDeletion.model_validate(payload))
    await db.commit()
    return True


async def _upsert_document(db: AsyncSession, payload: CatalogProductProjection) -> None:
    tombstone = await db.get(SearchTombstone, payload.product_id)
    if tombstone is not None and tombstone.deleted_at >= payload.updated_at:
        return
    document = await db.get(SearchDocument, payload.product_id)
    if document is not None and document.source_updated_at > payload.updated_at:
        return
    values = payload.model_dump()
    values["source_updated_at"] = values.pop("updated_at")
    if document is None:
        db.add(SearchDocument(**values))
        return
    for field, value in values.items():
        setattr(document, field, value)


async def _delete_document(db: AsyncSession, payload: CatalogProductDeletion) -> None:
    tombstone = await db.get(SearchTombstone, payload.product_id)
    if tombstone is None:
        tombstone = SearchTombstone(product_id=payload.product_id, deleted_at=payload.deleted_at)
        db.add(tombstone)
    elif tombstone.deleted_at < payload.deleted_at:
        tombstone.deleted_at = payload.deleted_at
    document = await db.get(SearchDocument, payload.product_id)
    if document is not None and document.source_updated_at <= payload.deleted_at:
        await db.delete(document)
