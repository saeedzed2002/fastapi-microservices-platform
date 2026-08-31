import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.models import (
    Category,
    OutboxMessage,
    Product,
    ProductMedia,
    ProductReview,
    ProductVariant,
)
from catalog_service.schemas import (
    AdminProductReviewListResponse,
    AdminProductReviewResponse,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    CheckoutVariantResponse,
    ProductCreate,
    ProductMediaAttach,
    ProductResponse,
    ProductReviewCreate,
    ProductReviewListResponse,
    ProductReviewModeration,
    ProductReviewReplyResponse,
    ProductReviewResponse,
    ProductReviewSubmissionResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
)


async def load_category_or_404(db: AsyncSession, category_id: UUID) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
    return category


async def load_category_by_slug_or_404(db: AsyncSession, slug: str) -> Category:
    category = await db.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
    return category


async def _validate_category_parent(
    db: AsyncSession, category: Category | None, parent_id: UUID | None
) -> None:
    if parent_id is None:
        return

    if category is not None and parent_id == category.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="category cannot be its own parent",
        )

    parent = await load_category_or_404(db, parent_id)
    if category is None:
        return

    visited: set[UUID] = set()
    current = parent
    while True:
        if current.id == category.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="category parent cannot be a descendant",
            )
        if current.id in visited:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="category hierarchy is inconsistent",
            )
        visited.add(current.id)
        if current.parent_id is None:
            return
        current = await load_category_or_404(db, current.parent_id)


async def category_response(category: Category) -> CategoryResponse:
    return CategoryResponse.model_validate(category)


async def list_categories(db: AsyncSession) -> list[CategoryResponse]:
    categories = await db.scalars(select(Category).order_by(Category.name, Category.created_at))
    return [await category_response(category) for category in categories]


async def create_category(db: AsyncSession, payload: CategoryCreate) -> Category:
    await _validate_category_parent(db, None, payload.parent_id)
    existing = await db.scalar(select(Category.id).where(Category.slug == payload.slug))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category slug exists")

    category = Category(**payload.model_dump())
    db.add(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="category could not be saved"
        ) from exc
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession, category: Category, payload: CategoryUpdate
) -> Category:
    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates:
        await _validate_category_parent(db, category, updates["parent_id"])
    if "slug" in updates:
        existing = await db.scalar(
            select(Category.id).where(Category.slug == updates["slug"], Category.id != category.id)
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category slug exists")

    for field, value in updates.items():
        setattr(category, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="category could not be saved"
        ) from exc
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, category: Category) -> None:
    child_id = await db.scalar(
        select(Category.id).where(Category.parent_id == category.id).limit(1)
    )
    if child_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="category has child categories"
        )
    product_id = await db.scalar(
        select(Product.id).where(Product.category_id == category.id).limit(1)
    )
    if product_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="category is assigned to products"
        )

    await db.delete(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="category is still in use"
        ) from exc


async def load_product_or_404(db: AsyncSession, product_id: UUID) -> Product:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return product


async def product_response(db: AsyncSession, product: Product) -> ProductResponse:
    media_ids = list(
        await db.scalars(
            select(ProductMedia.media_asset_id)
            .where(ProductMedia.product_id == product.id)
            .order_by(ProductMedia.sort_order, ProductMedia.created_at)
        )
    )
    return ProductResponse(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        status=product.status,
        brand_id=product.brand_id,
        category_id=product.category_id,
        price_amount=product.price_amount,
        currency=product.currency,
        attributes=product.attributes,
        media_asset_ids=media_ids,
        created_at=product.created_at,
        updated_at=product.updated_at,
        published_at=product.published_at,
    )


def encode_product_cursor(product: Product) -> str:
    if product.published_at is None:
        raise ValueError("a published product cursor requires published_at")
    payload = {
        "published_at": _utc_timestamp(product.published_at),
        "product_id": str(product.id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")


def decode_product_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        published_at = datetime.fromisoformat(str(payload["published_at"]).replace("Z", "+00:00"))
        product_id = UUID(str(payload["product_id"]))
    except (binascii.Error, KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid product cursor",
        ) from exc
    if published_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid product cursor",
        )
    return published_at.astimezone(UTC), product_id


async def list_published_products(
    db: AsyncSession, *, limit: int, cursor: str | None
) -> tuple[list[Product], str | None]:
    cursor_values = decode_product_cursor(cursor)
    conditions = [Product.status == "published", Product.published_at.is_not(None)]
    if cursor_values is not None:
        published_at, product_id = cursor_values
        conditions.append(
            or_(
                Product.published_at < published_at,
                and_(Product.published_at == published_at, Product.id < product_id),
            )
        )
    products = list(
        await db.scalars(
            select(Product)
            .where(*conditions)
            .order_by(desc(Product.published_at), desc(Product.id))
            .limit(limit + 1)
        )
    )
    has_next_page = len(products) > limit
    if has_next_page:
        products = products[:limit]
    next_cursor = encode_product_cursor(products[-1]) if has_next_page else None
    return products, next_cursor


def _utc_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _product_event_payload(product: Product) -> dict[str, Any]:
    return {
        "product_id": str(product.id),
        "slug": product.slug,
        "name": product.name,
        "description": product.description,
        "status": product.status,
        "brand_id": str(product.brand_id) if product.brand_id else None,
        "category_id": str(product.category_id) if product.category_id else None,
        "price_amount": str(product.price_amount),
        "currency": product.currency,
        "attributes": product.attributes,
        "published_at": _utc_timestamp(product.published_at),
        "updated_at": _utc_timestamp(product.updated_at),
    }


def _record_product_event(db: AsyncSession, *, event_type: str, product: Product) -> None:
    db.add(
        OutboxMessage(
            event_type=event_type,
            aggregate_type="product",
            aggregate_id=product.id,
            payload=_product_event_payload(product),
            correlation_id=product.id,
            causation_id=None,
            trace_id="0" * 32,
        )
    )


def _record_product_deletion(db: AsyncSession, *, product_id: UUID) -> None:
    db.add(
        OutboxMessage(
            event_type="product.deleted.v1",
            aggregate_type="product",
            aggregate_id=product_id,
            payload={
                "product_id": str(product_id),
                "deleted_at": _utc_timestamp(datetime.now(UTC)),
            },
            correlation_id=product_id,
            causation_id=None,
            trace_id="0" * 32,
        )
    )


async def create_product(db: AsyncSession, payload: ProductCreate) -> Product:
    if payload.category_id is not None:
        await load_category_or_404(db, payload.category_id)
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        await db.flush()
        _record_product_event(db, event_type="product.created.v1", product=product)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="product slug exists"
        ) from exc
    await db.refresh(product)
    return product


async def update_product(db: AsyncSession, product: Product, payload: ProductUpdate) -> Product:
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("category_id") is not None:
        await load_category_or_404(db, updates["category_id"])
    for field, value in updates.items():
        setattr(product, field, value)
    await db.flush()
    _record_product_event(db, event_type="product.updated.v1", product=product)
    await db.commit()
    await db.refresh(product)
    return product


async def publish_product(db: AsyncSession, product: Product) -> Product:
    product.status = "published"
    product.published_at = datetime.now(UTC)
    await db.flush()
    _record_product_event(db, event_type="product.updated.v1", product=product)
    await db.commit()
    await db.refresh(product)
    return product


async def delete_product(db: AsyncSession, product: Product) -> None:
    product_id = product.id
    await db.delete(product)
    _record_product_deletion(db, product_id=product_id)
    await db.commit()


async def attach_media(
    db: AsyncSession, product: Product, payload: ProductMediaAttach
) -> ProductMedia:
    existing = await db.scalar(
        select(ProductMedia).where(
            ProductMedia.product_id == product.id,
            ProductMedia.media_asset_id == payload.media_asset_id,
        )
    )
    if existing is not None:
        return existing
    relation = ProductMedia(product_id=product.id, **payload.model_dump())
    db.add(relation)
    await db.commit()
    await db.refresh(relation)
    return relation


async def add_variant(db: AsyncSession, product: Product, payload: VariantCreate) -> ProductVariant:
    variant = ProductVariant(product_id=product.id, **payload.model_dump())
    db.add(variant)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="variant SKU exists"
        ) from exc
    await db.refresh(variant)
    return variant


async def list_variants(db: AsyncSession, product_id: UUID) -> list[VariantResponse]:
    variants = await db.scalars(
        select(ProductVariant)
        .where(ProductVariant.product_id == product_id)
        .order_by(ProductVariant.created_at)
    )
    return [VariantResponse.model_validate(variant) for variant in variants]


async def checkout_variants(
    db: AsyncSession, variant_ids: list[UUID]
) -> list[CheckoutVariantResponse]:
    rows = await db.execute(
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.id.in_(variant_ids),
            ProductVariant.is_active.is_(True),
            Product.status == "published",
        )
    )
    snapshots = [
        CheckoutVariantResponse(
            variant_id=variant.id,
            sku=variant.sku,
            product_name=product.name,
            unit_amount=variant.price_amount
            if variant.price_amount is not None
            else product.price_amount,
            currency=product.currency,
            attributes=variant.attributes,
        )
        for variant, product in rows.tuples()
    ]
    if len({snapshot.variant_id for snapshot in snapshots}) != len(set(variant_ids)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="one or more variants are unavailable for checkout",
        )
    return snapshots


async def load_product_review_or_404(db: AsyncSession, review_id: UUID) -> ProductReview:
    review = await db.get(ProductReview, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product review not found"
        )
    return review


def _review_author_label(review: ProductReview) -> str:
    return "Store team" if review.author_role == "admin" else "Customer"


def _review_reply_response(review: ProductReview) -> ProductReviewReplyResponse:
    if review.parent_id is None:
        raise ValueError("a reply response requires a parent review")
    return ProductReviewReplyResponse(
        id=review.id,
        parent_id=review.parent_id,
        body=review.body,
        author_label=_review_author_label(review),
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _review_response(
    review: ProductReview, *, replies: list[ProductReview]
) -> ProductReviewResponse:
    return ProductReviewResponse(
        id=review.id,
        body=review.body,
        author_label=_review_author_label(review),
        created_at=review.created_at,
        updated_at=review.updated_at,
        replies=[_review_reply_response(reply) for reply in replies],
    )


def admin_product_review_response(review: ProductReview) -> AdminProductReviewResponse:
    return AdminProductReviewResponse(
        id=review.id,
        product_id=review.product_id,
        parent_id=review.parent_id,
        author_id=review.author_id,
        author_role=review.author_role,  # type: ignore[arg-type]
        body=review.body,
        status=review.status,  # type: ignore[arg-type]
        moderated_by=review.moderated_by,
        moderation_note=review.moderation_note,
        moderated_at=review.moderated_at,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def product_review_submission_response(review: ProductReview) -> ProductReviewSubmissionResponse:
    return ProductReviewSubmissionResponse(
        id=review.id,
        product_id=review.product_id,
        parent_id=review.parent_id,
        status=review.status,  # type: ignore[arg-type]
        created_at=review.created_at,
    )


def encode_product_review_cursor(review: ProductReview) -> str:
    payload = {
        "created_at": _utc_timestamp(review.created_at),
        "review_id": str(review.id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")


def decode_product_review_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        review_id = UUID(str(payload["review_id"]))
    except (binascii.Error, KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid product review cursor",
        ) from exc
    if created_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid product review cursor",
        )
    return created_at.astimezone(UTC), review_id


async def list_published_product_reviews(
    db: AsyncSession,
    *,
    product: Product,
    limit: int,
    cursor: str | None,
) -> ProductReviewListResponse:
    cursor_values = decode_product_review_cursor(cursor)
    conditions = [
        ProductReview.product_id == product.id,
        ProductReview.parent_id.is_(None),
        ProductReview.status == "approved",
    ]
    if cursor_values is not None:
        created_at, review_id = cursor_values
        conditions.append(
            or_(
                ProductReview.created_at < created_at,
                and_(ProductReview.created_at == created_at, ProductReview.id < review_id),
            )
        )
    reviews = list(
        await db.scalars(
            select(ProductReview)
            .where(*conditions)
            .order_by(desc(ProductReview.created_at), desc(ProductReview.id))
            .limit(limit + 1)
        )
    )
    has_next_page = len(reviews) > limit
    if has_next_page:
        reviews = reviews[:limit]
    review_ids = [review.id for review in reviews]
    replies_by_parent: dict[UUID, list[ProductReview]] = {review_id: [] for review_id in review_ids}
    if review_ids:
        replies = list(
            await db.scalars(
                select(ProductReview)
                .where(
                    ProductReview.parent_id.in_(review_ids),
                    ProductReview.status == "approved",
                )
                .order_by(ProductReview.created_at, ProductReview.id)
            )
        )
        for reply in replies:
            if reply.parent_id is not None:
                replies_by_parent[reply.parent_id].append(reply)
    return ProductReviewListResponse(
        items=[
            _review_response(review, replies=replies_by_parent[review.id]) for review in reviews
        ],
        next_cursor=encode_product_review_cursor(reviews[-1]) if has_next_page else None,
    )


async def create_product_review(
    db: AsyncSession,
    *,
    product: Product,
    payload: ProductReviewCreate,
    author_id: UUID,
    author_role: str,
    parent: ProductReview | None = None,
) -> ProductReview:
    if product.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    if parent is not None:
        if parent.product_id != product.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="review product mismatch"
            )
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="only one reply level is supported",
            )
        if parent.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="replies require an approved parent review",
            )
    review = ProductReview(
        product_id=product.id,
        parent_id=parent.id if parent is not None else None,
        author_id=author_id,
        author_role=author_role,
        body=payload.body,
        status="approved" if author_role == "admin" else "pending",
    )
    db.add(review)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="product review could not be saved",
        ) from exc
    await db.refresh(review)
    return review


async def list_admin_product_reviews(
    db: AsyncSession,
    *,
    status_filter: str | None,
    product_id: UUID | None,
    limit: int,
    cursor: str | None,
) -> AdminProductReviewListResponse:
    cursor_values = decode_product_review_cursor(cursor)
    conditions = []
    if status_filter is not None:
        conditions.append(ProductReview.status == status_filter)
    if product_id is not None:
        conditions.append(ProductReview.product_id == product_id)
    if cursor_values is not None:
        created_at, review_id = cursor_values
        conditions.append(
            or_(
                ProductReview.created_at < created_at,
                and_(ProductReview.created_at == created_at, ProductReview.id < review_id),
            )
        )
    reviews = list(
        await db.scalars(
            select(ProductReview)
            .where(*conditions)
            .order_by(desc(ProductReview.created_at), desc(ProductReview.id))
            .limit(limit + 1)
        )
    )
    has_next_page = len(reviews) > limit
    if has_next_page:
        reviews = reviews[:limit]
    return AdminProductReviewListResponse(
        items=[admin_product_review_response(review) for review in reviews],
        next_cursor=encode_product_review_cursor(reviews[-1]) if has_next_page else None,
    )


async def moderate_product_review(
    db: AsyncSession,
    *,
    review: ProductReview,
    payload: ProductReviewModeration,
    moderator_id: UUID,
) -> ProductReview:
    if payload.status == "approved" and review.parent_id is not None:
        parent = await db.get(ProductReview, review.parent_id)
        if parent is None or parent.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a reply cannot be approved while its parent is hidden",
            )
    review.status = payload.status
    review.moderated_by = moderator_id
    review.moderation_note = payload.moderation_note
    review.moderated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(review)
    return review
