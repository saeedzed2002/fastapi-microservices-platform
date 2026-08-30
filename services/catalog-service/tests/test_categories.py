import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from catalog_service.application import (
    _record_product_event,
    _validate_category_parent,
    create_category,
    create_product,
    decode_product_cursor,
    delete_category,
    encode_product_cursor,
)
from catalog_service.auth import require_administrator
from catalog_service.main import app
from catalog_service.models import Product
from catalog_service.schemas import CategoryCreate, ProductCreate
from platform_auth import AuthClaims


class FakeSession:
    def __init__(
        self,
        *,
        categories: dict[UUID, object] | None = None,
        scalar_results: list[object | None] | None = None,
    ) -> None:
        self.categories = categories or {}
        self.scalar_results = scalar_results or []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.refresh = AsyncMock()
        self.flush = AsyncMock()

    async def get(self, model: object, value: UUID) -> object | None:
        del model
        return self.categories.get(value)

    async def scalar(self, statement: object) -> object | None:
        del statement
        return self.scalar_results.pop(0) if self.scalar_results else None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def delete(self, value: object) -> None:
        self.deleted.append(value)


def test_category_routes_are_exposed_with_versioned_paths() -> None:
    paths = app.openapi()["paths"]

    assert set(paths["/api/v1/catalog/categories"]) == {"get", "post"}
    assert set(paths["/api/v1/catalog/categories/{slug}"]) == {"get"}
    assert set(paths["/api/v1/catalog/categories/{category_id}"]) == {"patch", "delete"}


def test_create_category_rejects_duplicate_slug_before_writing() -> None:
    async def exercise() -> None:
        session = FakeSession(scalar_results=[uuid4()])

        with pytest.raises(HTTPException) as error:
            await create_category(
                session,  # type: ignore[arg-type]
                CategoryCreate(name="Electronics", slug="electronics"),
            )

        assert error.value.status_code == 409
        assert error.value.detail == "category slug exists"
        assert not session.added
        session.commit.assert_not_awaited()

    asyncio.run(exercise())


def test_category_parent_cannot_be_self_or_descendant() -> None:
    async def exercise() -> None:
        category_id = uuid4()
        category = SimpleNamespace(id=category_id, parent_id=None)

        with pytest.raises(HTTPException, match="own parent") as self_parent_error:
            await _validate_category_parent(
                FakeSession(),  # type: ignore[arg-type]
                category,
                category_id,
            )
        assert self_parent_error.value.status_code == 422

        descendant_id = uuid4()
        descendant = SimpleNamespace(id=descendant_id, parent_id=category_id)
        with pytest.raises(HTTPException, match="descendant") as descendant_error:
            await _validate_category_parent(
                FakeSession(categories={descendant_id: descendant, category_id: category}),  # type: ignore[arg-type]
                category,
                descendant_id,
            )
        assert descendant_error.value.status_code == 422

    asyncio.run(exercise())


def test_delete_category_rejects_child_categories_and_product_assignments() -> None:
    async def exercise() -> None:
        category = SimpleNamespace(id=uuid4())

        with pytest.raises(HTTPException, match="child categories") as child_error:
            await delete_category(
                FakeSession(scalar_results=[uuid4()]),  # type: ignore[arg-type]
                category,
            )
        assert child_error.value.status_code == 409

        with pytest.raises(HTTPException, match="assigned to products") as product_error:
            await delete_category(
                FakeSession(scalar_results=[None, uuid4()]),  # type: ignore[arg-type]
                category,
            )
        assert product_error.value.status_code == 409

    asyncio.run(exercise())


def test_product_assignment_requires_an_existing_category() -> None:
    async def exercise() -> None:
        missing_category_id = uuid4()
        with pytest.raises(HTTPException) as error:
            await create_product(
                FakeSession(),  # type: ignore[arg-type]
                ProductCreate(
                    name="Phone",
                    slug="phone",
                    category_id=missing_category_id,
                    price_amount="150000",
                    currency="IRT",
                ),
            )

        assert error.value.status_code == 404
        assert error.value.detail == "category not found"

    asyncio.run(exercise())


def test_administrator_role_is_required_for_category_writes() -> None:
    now = datetime.now(UTC)
    customer_claims = AuthClaims(
        subject=uuid4(),
        token_id=uuid4(),
        roles=("customer",),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    administrator_claims = AuthClaims(
        subject=uuid4(),
        token_id=uuid4(),
        roles=("admin",),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    with pytest.raises(HTTPException) as error:
        require_administrator(customer_claims)
    assert error.value.status_code == 403

    require_administrator(administrator_claims)


def test_product_event_uses_a_complete_search_projection_payload() -> None:
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(),
        name="Phone",
        slug="phone",
        description="Searchable",
        status="published",
        price_amount="150000",
        currency="IRT",
        attributes={"color": "black"},
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    session = FakeSession()

    _record_product_event(session, event_type="product.updated.v1", product=product)  # type: ignore[arg-type]

    event = session.added[0]
    assert event.event_type == "product.updated.v1"
    assert event.payload["product_id"] == str(product.id)
    assert event.payload["published_at"].endswith("Z")


def test_product_cursor_round_trip_and_invalid_input() -> None:
    now = datetime.now(UTC)
    product = Product(id=uuid4(), published_at=now)

    assert decode_product_cursor(encode_product_cursor(product)) == (now, product.id)
    with pytest.raises(HTTPException, match="invalid product cursor") as error:
        decode_product_cursor("not-a-valid-cursor")
    assert error.value.status_code == 422
