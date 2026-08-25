import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.application import provision_customer
from customer_service.auth import current_user
from customer_service.config import get_settings
from customer_service.db import dispose_engine, get_session
from customer_service.models import Address, Customer
from customer_service.schemas import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    CustomerResponse,
    ProfileUpsert,
)
from customer_service.workers.identity_consumer import consume_identity_events
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    consumer_task: asyncio.Task[None] | None = None
    if settings.kafka_consumer_enabled:
        consumer_task = asyncio.create_task(consume_identity_events(settings, stop))
    logger.info("service_started")
    yield
    stop.set()
    if consumer_task is not None:
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Customer Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/customers/me", response_model=CustomerResponse)
async def get_profile(
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> CustomerResponse:
    customer = await db.get(Customer, claims.subject)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="customer profile not ready"
        )
    return CustomerResponse.model_validate(customer)


@app.put("/api/v1/customers/me", response_model=CustomerResponse)
async def upsert_profile(
    payload: ProfileUpsert,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> CustomerResponse:
    customer = await db.get(Customer, claims.subject)
    if customer is None:
        customer = await provision_customer(
            db, user_id=claims.subject, email=f"{claims.subject}@unknown.invalid"
        )
    customer.display_name = payload.display_name
    customer.phone = payload.phone
    customer.avatar_media_id = payload.avatar_media_id
    await db.commit()
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer)


@app.get("/api/v1/customers/me/addresses", response_model=list[AddressResponse])
async def list_addresses(
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[AddressResponse]:
    rows = await db.scalars(
        select(Address).where(Address.customer_id == claims.subject).order_by(Address.created_at)
    )
    return [AddressResponse.model_validate(row) for row in rows]


@app.post(
    "/api/v1/customers/me/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_address(
    payload: AddressCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> AddressResponse:
    if await db.get(Customer, claims.subject) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="customer profile not ready"
        )
    if payload.is_default:
        await db.execute(
            update(Address).where(Address.customer_id == claims.subject).values(is_default=False)
        )
    address = Address(customer_id=claims.subject, **payload.model_dump())
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return AddressResponse.model_validate(address)


@app.patch("/api/v1/customers/me/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: str,
    payload: AddressUpdate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> AddressResponse:
    from uuid import UUID

    try:
        parsed_id = UUID(address_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="address not found"
        ) from exc
    address = await db.scalar(
        select(Address).where(Address.id == parsed_id, Address.customer_id == claims.subject)
    )
    if address is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="address not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default"):
        await db.execute(
            update(Address).where(Address.customer_id == claims.subject).values(is_default=False)
        )
    for key, value in changes.items():
        setattr(address, key, value)
    await db.commit()
    await db.refresh(address)
    return AddressResponse.model_validate(address)


@app.delete("/api/v1/customers/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: str,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    from uuid import UUID

    try:
        parsed_id = UUID(address_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="address not found"
        ) from exc
    address = await db.scalar(
        select(Address).where(Address.id == parsed_id, Address.customer_id == claims.subject)
    )
    if address is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="address not found")
    await db.delete(address)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP customer_service_up Service availability\n"
        "# TYPE customer_service_up gauge\n"
        "customer_service_up 1\n"
    )
