import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.application import (
    add_variant,
    attach_media,
    category_response,
    checkout_variants,
    create_category,
    create_product,
    delete_category,
    list_categories,
    list_variants,
    load_category_by_slug_or_404,
    load_category_or_404,
    load_product_or_404,
    product_response,
    publish_product,
    update_category,
    update_product,
)
from catalog_service.auth import current_user, require_catalog_admin
from catalog_service.config import get_settings
from catalog_service.db import dispose_engine, get_session
from catalog_service.models import Product
from catalog_service.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    CheckoutVariantRequest,
    CheckoutVariantResponse,
    ProductCreate,
    ProductMediaAttach,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
)
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("service_started")
    yield
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Catalog Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/catalog/products", response_model=list[ProductResponse])
async def list_products(db: AsyncSession = Depends(get_session)) -> list[ProductResponse]:
    products = await db.scalars(
        select(Product).where(Product.status == "published").order_by(Product.published_at.desc())
    )
    return [await product_response(db, product) for product in products]


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
    require_catalog_admin(claims)
    return await category_response(await create_category(db, payload))


@app.patch("/api/v1/catalog/categories/{category_id}", response_model=CategoryResponse)
async def update_category_endpoint(
    category_id: UUID,
    payload: CategoryUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    require_catalog_admin(claims)
    category = await load_category_or_404(db, category_id)
    return await category_response(await update_category(db, category, payload))


@app.delete("/api/v1/catalog/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    require_catalog_admin(claims)
    await delete_category(db, await load_category_or_404(db, category_id))


@app.get("/api/v1/catalog/products/{slug}", response_model=ProductResponse)
async def get_product(slug: str, db: AsyncSession = Depends(get_session)) -> ProductResponse:
    product = await db.scalar(
        select(Product).where(Product.slug == slug, Product.status == "published")
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return await product_response(db, product)


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
    require_catalog_admin(claims)
    return await product_response(db, await create_product(db, payload))


@app.patch("/api/v1/catalog/products/{product_id}", response_model=ProductResponse)
async def update_product_endpoint(
    product_id: UUID,
    payload: ProductUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_catalog_admin(claims)
    product = await load_product_or_404(db, product_id)
    return await product_response(db, await update_product(db, product, payload))


@app.post("/api/v1/catalog/products/{product_id}/publish", response_model=ProductResponse)
async def publish_product_endpoint(
    product_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProductResponse:
    require_catalog_admin(claims)
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
    require_catalog_admin(claims)
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
    require_catalog_admin(claims)
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
async def metrics() -> str:
    return (
        "# HELP catalog_service_up Service availability\n"
        "# TYPE catalog_service_up gauge\n"
        "catalog_service_up 1\n"
    )
