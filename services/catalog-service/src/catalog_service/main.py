import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.application import (
    add_variant,
    admin_product_review_response,
    attach_media,
    brand_response,
    category_response,
    checkout_variants,
    create_brand,
    create_category,
    create_product,
    create_product_review,
    delete_brand,
    delete_category,
    delete_product,
    detach_product_media,
    list_admin_product_reviews,
    list_administrator_products,
    list_brands,
    list_categories,
    list_published_product_reviews,
    list_published_products,
    list_variants,
    load_brand_by_slug_or_404,
    load_brand_or_404,
    load_category_by_slug_or_404,
    load_category_or_404,
    load_product_media_or_404,
    load_product_or_404,
    load_product_review_or_404,
    load_product_variant_or_404,
    moderate_product_review,
    product_response,
    product_review_submission_response,
    publish_product,
    restore_product,
    retire_variant,
    update_brand,
    update_category,
    update_product,
    update_product_media,
    update_variant,
)
from catalog_service.auth import current_user, require_administrator
from catalog_service.config import get_settings
from catalog_service.db import dispose_engine, get_session
from catalog_service.media import HttpMediaCatalogGateway, verify_media_reference_proof
from catalog_service.models import Product, ProductMedia
from catalog_service.schemas import (
    AdminProductReviewListResponse,
    AdminProductReviewResponse,
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    CheckoutVariantRequest,
    CheckoutVariantResponse,
    ProductCreate,
    ProductListResponse,
    ProductMediaAttach,
    ProductMediaResponse,
    ProductMediaUpdate,
    ProductResponse,
    ProductReviewCreate,
    ProductReviewListResponse,
    ProductReviewModeration,
    ProductReviewSubmissionResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)
from catalog_service.workers.kafka import publish_outbox
from platform_auth import AuthClaims
from platform_observability import configure_application, metrics_response

settings = get_settings()
logger = logging.getLogger(settings.service_name)
media_gateway = HttpMediaCatalogGateway(settings)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task: asyncio.Task[None] | None = None
    if settings.kafka_publisher_enabled:
        task = asyncio.create_task(publish_outbox(settings, stop))
    logger.info("service_started")
    yield
    stop.set()
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await media_gateway.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Catalog Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/catalog/products", response_model=ProductListResponse)
async def list_products(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
    db: AsyncSession = Depends(get_session),
) -> ProductListResponse:
    products, next_cursor = await list_published_products(db, limit=limit, cursor=cursor)
    return ProductListResponse(
        items=[await product_response(db, product) for product in products],
        next_cursor=next_cursor,
    )


@app.get("/api/v1/catalog/categories", response_model=list[CategoryResponse])
async def list_categories_endpoint(
    db: AsyncSession = Depends(get_session),
) -> list[CategoryResponse]:
    return await list_categories(db)


@app.get("/api/v1/catalog/categories/{slug}", response_model=CategoryResponse)
async def get_category(slug: str, db: AsyncSession = Depends(get_session)) -> CategoryResponse:
    return await category_response(await load_category_by_slug_or_404(db, slug))


@app.get("/api/v1/catalog/brands", response_model=list[BrandResponse])
async def list_brands_endpoint(db: AsyncSession = Depends(get_session)) -> list[BrandResponse]:
    return await list_brands(db)


@app.get("/api/v1/catalog/brands/{slug}", response_model=BrandResponse)
async def get_brand(slug: str, db: AsyncSession = Depends(get_session)) -> BrandResponse:
    return await brand_response(await load_brand_by_slug_or_404(db, slug))


@app.post(
    "/api/v1/catalog/brands",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand_endpoint(
    payload: BrandCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> BrandResponse:
    require_administrator(claims)
    return await brand_response(await create_brand(db, payload))


@app.patch("/api/v1/catalog/brands/{brand_id}", response_model=BrandResponse)
async def update_brand_endpoint(
    brand_id: UUID,
    payload: BrandUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> BrandResponse:
    require_administrator(claims)
    return await brand_response(
        await update_brand(db, await load_brand_or_404(db, brand_id), payload)
    )


@app.delete("/api/v1/catalog/brands/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_endpoint(
    brand_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    require_administrator(claims)
    await delete_brand(db, await load_brand_or_404(db, brand_id))


@app.post(
    "/api/v1/catalog/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category_endpoint(
    payload: CategoryCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    require_administrator(claims)
    return await category_response(await create_category(db, payload))


@app.patch("/api/v1/catalog/categories/{category_id}", response_model=CategoryResponse)
async def update_category_endpoint(
    category_id: UUID,
    payload: CategoryUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    require_administrator(claims)
    category = await load_category_or_404(db, category_id)
    return await category_response(await update_category(db, category, payload))


@app.delete("/api/v1/catalog/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    require_administrator(claims)
    await delete_category(db, await load_category_or_404(db, category_id))


@app.get("/api/v1/catalog/admin/products", response_model=ProductListResponse)
async def list_administrator_products_endpoint(
    product_status: Literal["draft", "published", "archived"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductListResponse:
    require_administrator(claims)
    products, next_cursor = await list_administrator_products(
        db,
        status_filter=product_status,
        limit=limit,
        cursor=cursor,
    )
    return ProductListResponse(
        items=[await product_response(db, product) for product in products],
        next_cursor=next_cursor,
    )


@app.get("/api/v1/catalog/admin/products/{product_id}", response_model=ProductResponse)
async def get_administrator_product_endpoint(
    product_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_administrator(claims)
    return await product_response(db, await load_product_or_404(db, product_id))


@app.get("/api/v1/catalog/products/{slug}", response_model=ProductResponse)
async def get_product(slug: str, db: AsyncSession = Depends(get_session)) -> ProductResponse:
    product = await db.scalar(
        select(Product).where(Product.slug == slug, Product.status == "published")
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return await product_response(db, product)


@app.get("/api/internal/v1/catalog/media-assets/{asset_id}/reference-status")
async def product_media_reference_status(
    asset_id: UUID,
    expires_at: int = Query(ge=1),
    media_access_proof: str = Header(alias="X-Media-Access-Proof"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    verify_media_reference_proof(
        secret=settings.media_internal_access_secret,
        provided_proof=media_access_proof,
        asset_id=asset_id,
        expires_at=expires_at,
    )
    referenced = await db.scalar(
        select(ProductMedia.media_asset_id).where(ProductMedia.media_asset_id == asset_id).limit(1)
    )
    return {"referenced": referenced is not None}


@app.get(
    "/api/v1/catalog/products/{slug}/reviews",
    response_model=ProductReviewListResponse,
)
async def list_product_reviews_endpoint(
    slug: str,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=256),
    db: AsyncSession = Depends(get_session),
) -> ProductReviewListResponse:
    product = await db.scalar(
        select(Product).where(Product.slug == slug, Product.status == "published")
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return await list_published_product_reviews(db, product=product, limit=limit, cursor=cursor)


@app.post(
    "/api/v1/catalog/products/{product_id}/reviews",
    response_model=ProductReviewSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_review_endpoint(
    product_id: UUID,
    payload: ProductReviewCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductReviewSubmissionResponse:
    review = await create_product_review(
        db,
        product=await load_product_or_404(db, product_id),
        payload=payload,
        author_id=claims.subject,
        author_role="admin" if "admin" in claims.roles else "customer",
    )
    return product_review_submission_response(review)


@app.post(
    "/api/v1/catalog/reviews/{review_id}/replies",
    response_model=ProductReviewSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_review_reply_endpoint(
    review_id: UUID,
    payload: ProductReviewCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductReviewSubmissionResponse:
    parent = await load_product_review_or_404(db, review_id)
    review = await create_product_review(
        db,
        product=await load_product_or_404(db, parent.product_id),
        payload=payload,
        author_id=claims.subject,
        author_role="admin" if "admin" in claims.roles else "customer",
        parent=parent,
    )
    return product_review_submission_response(review)


@app.get(
    "/api/v1/catalog/admin/reviews",
    response_model=AdminProductReviewListResponse,
)
async def list_admin_product_reviews_endpoint(
    review_status: Literal["pending", "approved", "rejected"] | None = Query(
        default=None,
        alias="status",
    ),
    product_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=256),
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> AdminProductReviewListResponse:
    require_administrator(claims)
    return await list_admin_product_reviews(
        db,
        status_filter=review_status,
        product_id=product_id,
        limit=limit,
        cursor=cursor,
    )


@app.post(
    "/api/v1/catalog/admin/reviews/{review_id}/moderation",
    response_model=AdminProductReviewResponse,
)
async def moderate_product_review_endpoint(
    review_id: UUID,
    payload: ProductReviewModeration,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> AdminProductReviewResponse:
    require_administrator(claims)
    review = await moderate_product_review(
        db,
        review=await load_product_review_or_404(db, review_id),
        payload=payload,
        moderator_id=claims.subject,
    )
    return admin_product_review_response(review)


@app.post(
    "/api/v1/catalog/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_endpoint(
    payload: ProductCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_administrator(claims)
    return await product_response(db, await create_product(db, payload))


@app.patch("/api/v1/catalog/products/{product_id}", response_model=ProductResponse)
async def update_product_endpoint(
    product_id: UUID,
    payload: ProductUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_administrator(claims)
    product = await load_product_or_404(db, product_id)
    return await product_response(db, await update_product(db, product, payload))


@app.delete("/api/v1/catalog/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_endpoint(
    product_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    require_administrator(claims)
    await delete_product(db, await load_product_or_404(db, product_id))


@app.post("/api/v1/catalog/products/{product_id}/restore", response_model=ProductResponse)
async def restore_product_endpoint(
    product_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_administrator(claims)
    product = await restore_product(db, await load_product_or_404(db, product_id))
    return await product_response(db, product)


@app.post("/api/v1/catalog/products/{product_id}/publish", response_model=ProductResponse)
async def publish_product_endpoint(
    product_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_administrator(claims)
    product = await load_product_or_404(db, product_id)
    return await product_response(db, await publish_product(db, product))


@app.post(
    "/api/v1/catalog/products/{product_id}/media",
    response_model=ProductMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_media_endpoint(
    product_id: UUID,
    payload: ProductMediaAttach,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductMediaResponse:
    require_administrator(claims)
    await media_gateway.validate_product_image(
        asset_id=payload.media_asset_id,
        owner_subject_id=claims.subject,
    )
    product = await load_product_or_404(db, product_id)
    relation = await attach_media(db, product, payload)
    return ProductMediaResponse.model_validate(relation)


@app.patch(
    "/api/v1/catalog/products/{product_id}/media/{media_asset_id}",
    response_model=ProductMediaResponse,
)
async def update_product_media_endpoint(
    product_id: UUID,
    media_asset_id: UUID,
    payload: ProductMediaUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductMediaResponse:
    require_administrator(claims)
    await load_product_or_404(db, product_id)
    relation = await update_product_media(
        db,
        await load_product_media_or_404(db, product_id=product_id, media_asset_id=media_asset_id),
        payload,
    )
    return ProductMediaResponse.model_validate(relation)


@app.delete(
    "/api/v1/catalog/products/{product_id}/media/{media_asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_product_media_endpoint(
    product_id: UUID,
    media_asset_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    require_administrator(claims)
    await load_product_or_404(db, product_id)
    await detach_product_media(
        db,
        await load_product_media_or_404(db, product_id=product_id, media_asset_id=media_asset_id),
    )


@app.post(
    "/api/v1/catalog/products/{product_id}/variants",
    response_model=VariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_variant_endpoint(
    product_id: UUID,
    payload: VariantCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> VariantResponse:
    require_administrator(claims)
    product = await load_product_or_404(db, product_id)
    return VariantResponse.model_validate(await add_variant(db, product, payload))


@app.get("/api/v1/catalog/products/{product_id}/variants", response_model=list[VariantResponse])
async def list_variants_endpoint(
    product_id: UUID, db: AsyncSession = Depends(get_session)
) -> list[VariantResponse]:
    product = await load_product_or_404(db, product_id)
    if product.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return await list_variants(db, product_id, active_only=True)


@app.get(
    "/api/v1/catalog/admin/products/{product_id}/variants", response_model=list[VariantResponse]
)
async def list_administrator_variants_endpoint(
    product_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[VariantResponse]:
    require_administrator(claims)
    await load_product_or_404(db, product_id)
    return await list_variants(db, product_id)


@app.patch(
    "/api/v1/catalog/products/{product_id}/variants/{variant_id}",
    response_model=VariantResponse,
)
async def update_variant_endpoint(
    product_id: UUID,
    variant_id: UUID,
    payload: VariantUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> VariantResponse:
    require_administrator(claims)
    await load_product_or_404(db, product_id)
    variant = await update_variant(
        db,
        await load_product_variant_or_404(db, product_id=product_id, variant_id=variant_id),
        payload,
    )
    return VariantResponse.model_validate(variant)


@app.delete(
    "/api/v1/catalog/products/{product_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def retire_variant_endpoint(
    product_id: UUID,
    variant_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    require_administrator(claims)
    await load_product_or_404(db, product_id)
    await retire_variant(
        db,
        await load_product_variant_or_404(db, product_id=product_id, variant_id=variant_id),
    )


@app.post(
    "/api/v1/catalog/checkout/variants",
    response_model=list[CheckoutVariantResponse],
)
async def checkout_variants_endpoint(
    payload: CheckoutVariantRequest,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[CheckoutVariantResponse]:
    return await checkout_variants(db, payload.variant_ids)


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()
