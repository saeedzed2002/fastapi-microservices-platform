import os

import pytest

from tests.e2e.checkout_workflow import run_checkout_workflow
from tests.e2e.returns_workflow import run_returns_workflow

pytestmark = pytest.mark.e2e


def test_post_delivery_return_restocks_only_after_receipt_and_correlates_refund() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    run_returns_workflow(run_checkout_workflow())
