from uuid import uuid4

import pytest
from pydantic import ValidationError

from cart_service.schemas import CartConsumeRequest


def test_cart_consume_rejects_duplicate_variants() -> None:
    variant_id = uuid4()

    with pytest.raises(ValidationError, match="duplicate variant"):
        CartConsumeRequest(
            expected_version=1,
            items=[
                {"variant_id": variant_id, "quantity": 1},
                {"variant_id": variant_id, "quantity": 1},
            ],
        )
