import os

import pytest

from tests.e2e.checkout_workflow import run_checkout_workflow
from tests.e2e.shipping_workflow import run_shipping_workflow

pytestmark = pytest.mark.e2e


def test_shipping_transition_updates_the_order_projection_through_kafka() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    run_shipping_workflow(run_checkout_workflow())
