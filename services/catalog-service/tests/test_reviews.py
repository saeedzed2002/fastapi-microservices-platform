import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from catalog_service.application import (
    create_product_review,
    decode_product_review_cursor,
    encode_product_review_cursor,
    list_published_product_reviews,
    moderate_product_review,
)
from catalog_service.main import app
from catalog_service.models import Product, ProductReview
from catalog_service.schemas import (
    ProductReviewCreate,
    ProductReviewModeration,
    ProductReviewResponse,
)


class ReviewSession:
    def __init__(self, *, parents: dict[object, ProductReview] | None = None) -> None:
        self.parents = parents or {}
        self.added: list[object] = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.rollback = AsyncMock()

    def add(self, value: object) -> None:
        self.added.append(value)

    async def get(self, model: object, value: object) -> ProductReview | None:
        del model
        return self.parents.get(value)


class ReviewListingSession:
    def __init__(self, results: list[list[ProductReview]]) -> None:
        self.results = results

    async def scalars(self, statement: object) -> list[ProductReview]:
        del statement
        return self.results.pop(0)


def test_review_routes_are_exposed_without_a_public_admin_queue() -> None:
    paths = app.openapi()["paths"]

    assert "get" in paths["/api/v1/catalog/products/{slug}/reviews"]
    assert "post" in paths["/api/v1/catalog/products/{product_id}/reviews"]
    assert "post" in paths["/api/v1/catalog/reviews/{review_id}/replies"]
    assert "get" in paths["/api/v1/catalog/admin/reviews"]
    assert "post" in paths["/api/v1/catalog/admin/reviews/{review_id}/moderation"]


def test_review_submission_is_trimmed_and_customer_submissions_are_pending() -> None:
    async def exercise() -> None:
        product = Product(id=uuid4(), status="published")
        db = ReviewSession()
        review = await create_product_review(
            db,  # type: ignore[arg-type]
            product=product,
            payload=ProductReviewCreate(body="  Useful and specific feedback.  "),
            author_id=uuid4(),
            author_role="customer",
        )

        assert review.body == "Useful and specific feedback."
        assert review.status == "pending"
        assert db.added == [review]
        db.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_review_replies_require_an_approved_root_and_one_level_only() -> None:
    async def exercise() -> None:
        product = Product(id=uuid4(), status="published")
        pending_parent = ProductReview(
            id=uuid4(),
            product_id=product.id,
            author_id=uuid4(),
            author_role="customer",
            body="Pending",
            status="pending",
        )
        with pytest.raises(HTTPException, match="approved parent") as pending_error:
            await create_product_review(
                ReviewSession(),  # type: ignore[arg-type]
                product=product,
                payload=ProductReviewCreate(body="Reply"),
                author_id=uuid4(),
                author_role="customer",
                parent=pending_parent,
            )
        assert pending_error.value.status_code == 409

        nested_parent = ProductReview(
            id=uuid4(),
            product_id=product.id,
            parent_id=uuid4(),
            author_id=uuid4(),
            author_role="customer",
            body="Existing reply",
            status="approved",
        )
        with pytest.raises(HTTPException, match="one reply level") as nested_error:
            await create_product_review(
                ReviewSession(),  # type: ignore[arg-type]
                product=product,
                payload=ProductReviewCreate(body="Nested reply"),
                author_id=uuid4(),
                author_role="customer",
                parent=nested_parent,
            )
        assert nested_error.value.status_code == 422

    asyncio.run(exercise())


def test_review_moderation_does_not_publish_a_reply_with_a_hidden_parent() -> None:
    async def exercise() -> None:
        hidden_parent = ProductReview(
            id=uuid4(),
            product_id=uuid4(),
            author_id=uuid4(),
            author_role="customer",
            body="Hidden",
            status="rejected",
        )
        reply = ProductReview(
            id=uuid4(),
            product_id=hidden_parent.product_id,
            parent_id=hidden_parent.id,
            author_id=uuid4(),
            author_role="customer",
            body="Reply",
            status="pending",
        )
        db = ReviewSession(parents={hidden_parent.id: hidden_parent})

        with pytest.raises(HTTPException, match="parent is hidden") as error:
            await moderate_product_review(
                db,  # type: ignore[arg-type]
                review=reply,
                payload=ProductReviewModeration(status="approved"),
                moderator_id=uuid4(),
            )
        assert error.value.status_code == 409
        db.commit.assert_not_awaited()

    asyncio.run(exercise())


def test_public_review_page_contains_only_approved_content_without_author_identifiers() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        product = Product(id=uuid4(), status="published")
        root = ProductReview(
            id=uuid4(),
            product_id=product.id,
            author_id=uuid4(),
            author_role="customer",
            body="Approved review",
            status="approved",
            created_at=now,
            updated_at=now,
        )
        reply = ProductReview(
            id=uuid4(),
            product_id=product.id,
            parent_id=root.id,
            author_id=uuid4(),
            author_role="admin",
            body="Approved reply",
            status="approved",
            created_at=now,
            updated_at=now,
        )
        page = await list_published_product_reviews(
            ReviewListingSession([[root], [reply]]),  # type: ignore[arg-type]
            product=product,
            limit=20,
            cursor=None,
        )

        assert page.items[0].author_label == "Customer"
        assert page.items[0].replies[0].author_label == "Store team"
        assert "author_id" not in ProductReviewResponse.model_fields
        assert "status" not in ProductReviewResponse.model_fields

    asyncio.run(exercise())


def test_review_cursor_round_trip_and_blank_body_rejection() -> None:
    now = datetime.now(UTC)
    review = ProductReview(id=uuid4(), created_at=now)

    assert decode_product_review_cursor(encode_product_review_cursor(review)) == (now, review.id)
    with pytest.raises(ValueError, match="must not be blank"):
        ProductReviewCreate(body="   ")
    with pytest.raises(ValueError, match="must not be blank"):
        ProductReviewModeration(status="rejected", moderation_note="   ")
