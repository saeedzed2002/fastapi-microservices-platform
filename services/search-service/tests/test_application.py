import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from search_service.application import (
    _delete_document,
    _upsert_document,
    decode_cursor,
    encode_cursor,
    search_products,
)
from search_service.models import SearchDocument, SearchTombstone
from search_service.schemas import CatalogProductDeletion, CatalogProductProjection


def test_search_cursor_round_trip() -> None:
    assert decode_cursor(encode_cursor(42)) == 42


def test_invalid_search_cursor_is_rejected() -> None:
    try:
        decode_cursor("not-a-cursor")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
    else:
        raise AssertionError("invalid cursor was accepted")


@pytest.mark.parametrize(
    "cursor",
    (
        encode_cursor(10_001),
        "eyJvZmZzZXQiOnRydWV9",
        "eyJvZmZzZXQiOi0xfQ",
    ),
)
def test_search_cursor_rejects_non_integer_and_out_of_range_offsets(cursor: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_cursor(cursor)

    assert exc_info.value.status_code == 422


class ProjectionSession:
    def __init__(self) -> None:
        self.documents: dict[object, SearchDocument] = {}
        self.tombstones: dict[object, SearchTombstone] = {}
        self.added: list[object] = []
        self.deleted: list[object] = []

    async def get(
        self, model: type[SearchDocument] | type[SearchTombstone], key: object
    ) -> object | None:
        if model is SearchDocument:
            return self.documents.get(key)
        if model is SearchTombstone:
            return self.tombstones.get(key)
        raise AssertionError(f"unexpected model {model}")

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, SearchDocument):
            self.documents[value.product_id] = value
        if isinstance(value, SearchTombstone):
            self.tombstones[value.product_id] = value

    async def delete(self, value: object) -> None:
        self.deleted.append(value)
        if isinstance(value, SearchDocument):
            self.documents.pop(value.product_id, None)


def _projection(
    *, product_id: object, updated_at: datetime, name: str = "New name"
) -> CatalogProductProjection:
    return CatalogProductProjection(
        product_id=product_id,
        slug="projection-product",
        name=name,
        description="Search projection",
        status="published",
        price_amount=Decimal("12.50"),
        currency="usd",
        updated_at=updated_at,
        published_at=updated_at,
    )


def _document(*, product_id: object, updated_at: datetime, name: str) -> SearchDocument:
    return SearchDocument(
        product_id=product_id,
        slug="projection-product",
        name=name,
        description="Search projection",
        status="published",
        brand_id=None,
        category_id=None,
        price_amount=Decimal("12.50"),
        currency="USD",
        attributes={},
        published_at=updated_at,
        source_updated_at=updated_at,
    )


def test_stale_catalog_upsert_cannot_overwrite_a_newer_search_projection() -> None:
    async def exercise() -> None:
        product_id = uuid4()
        now = datetime.now(UTC)
        session = ProjectionSession()
        document = _document(product_id=product_id, updated_at=now, name="Current name")
        session.documents[product_id] = document

        await _upsert_document(
            session,  # type: ignore[arg-type]
            _projection(product_id=product_id, updated_at=now - timedelta(seconds=1)),
        )

        assert document.name == "Current name"
        assert session.added == []

    asyncio.run(exercise())


def test_newer_catalog_delete_tombstones_and_removes_only_an_older_projection() -> None:
    async def exercise() -> None:
        product_id = uuid4()
        now = datetime.now(UTC)
        session = ProjectionSession()
        document = _document(
            product_id=product_id,
            updated_at=now - timedelta(seconds=1),
            name="Old",
        )
        session.documents[product_id] = document

        await _delete_document(
            session,  # type: ignore[arg-type]
            CatalogProductDeletion(product_id=product_id, deleted_at=now),
        )

        assert session.tombstones[product_id].deleted_at == now
        assert session.deleted == [document]
        assert product_id not in session.documents

    asyncio.run(exercise())


def test_search_rejects_inverted_price_range_before_querying_the_database() -> None:
    class NoQuerySession:
        async def execute(self, _: object) -> None:
            raise AssertionError("invalid price range must not query the database")

    async def exercise() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await search_products(
                NoQuerySession(),  # type: ignore[arg-type]
                query="catalog",
                cursor=None,
                limit=20,
                category_id=None,
                brand_id=None,
                currency=None,
                min_price=Decimal("10.00"),
                max_price=Decimal("9.99"),
            )
        assert exc_info.value.status_code == 422

    asyncio.run(exercise())
