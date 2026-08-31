import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.application import (
    add_variant,
    admin_product_review_response,
    attach_media,
    category_response,
    checkout_variants,
    create_category,
    create_product,
    create_product_review,
    delete_category,
    delete_product,
    list_admin_product_reviews,
    list_categories,
    list_published_product_reviews,
    list_published_products,
    list_variants,
    load_category_by_slug_or_404,
    load_category_or_404,
    load_product_or_404,
    load_product_review_or_404,
    moderate_product_review,
    product_response,
    product_review_submission_response,
    publish_product,
    update_category,
    update_product,
)
from catalog_service.auth import current_user, require_administrator
from catalog_service.config import get_settings
from catalog_service.db import dispose_engine, get_session
from catalog_service.media import HttpMediaCatalogGateway
from catalog_service.models import Product
from catalog_service.schemas import (
    AdminProductReviewListResponse,
    AdminProductReviewResponse,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    CheckoutVariantRequest,
    CheckoutVariantResponse,
    ProductCreate,
    ProductListResponse,
    ProductMediaAttach,
    ProductResponse,
    ProductReviewCreate,
    ProductReviewListResponse,
    ProductReviewModeration,
    ProductReviewSubmissionResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
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


@app.get("/api/v1/catalog/products/{slug}", response_model=ProductResponse)
async def get_product(slug: str, db: AsyncSession = Depends(get_session)) -> ProductResponse:
    product = await db.scalar(
        select(Product).where(Product.slug == slug, Product.status == "published")
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return await product_response(db, product)


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
    status_code=status.HTTP_201_CREATED,
)
async def attach_media_endpoint(
    product_id: UUID,
    payload: ProductMediaAttach,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    require_administrator(claims)
    await media_gateway.validate_product_image(
        asset_id=payload.media_asset_id,
        owner_subject_id=claims.subject,
    )
    product = await load_product_or_404(db, product_id)
    relation = await attach_media(db, product, payload)
    return {"product_media_id": str(relation.id)}


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
    await load_product_or_404(db, product_id)
    return await list_variants(db, product_id)


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
