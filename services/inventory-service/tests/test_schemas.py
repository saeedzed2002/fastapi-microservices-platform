import pytest
from pydantic import ValidationError

from inventory_service.schemas import StockAdjustmentCreate, StockItemCreate


def test_stock_item_normalizes_sku() -> None:
    stock_item = StockItemCreate(sku=" sku-1 ", initial_quantity=1)
    assert stock_item.sku == "SKU-1"


def test_stock_adjustment_rejects_zero_delta() -> None:
    with pytest.raises(ValidationError):
        StockAdjustmentCreate(quantity_delta=0, reason="correction", idempotency_key="request-1")
