from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.models import Product, ProductMedia, ProductVariant
from catalog_service.schemas import (
    ProductCreate,
    ProductMediaAttach,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
)


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


async def create_product(db: AsyncSession, payload: ProductCreate) -> Product:
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="product slug exists"
        ) from exc
    await db.refresh(product)
    return product


async def update_product(db: AsyncSession, product: Product, payload: ProductUpdate) -> Product:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return product


async def publish_product(db: AsyncSession, product: Product) -> Product:
    product.status = "published"
    product.published_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(product)
    return product


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
