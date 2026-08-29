from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.models import Category, Product, ProductMedia, ProductVariant
from catalog_service.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    CheckoutVariantResponse,
    ProductCreate,
    ProductMediaAttach,
    ProductResponse,
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


async def create_product(db: AsyncSession, payload: ProductCreate) -> Product:
    if payload.category_id is not None:
        await load_category_or_404(db, payload.category_id)
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
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("category_id") is not None:
        await load_category_or_404(db, updates["category_id"])
    for field, value in updates.items():
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
