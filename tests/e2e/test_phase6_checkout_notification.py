import os

import pytest

from tests.e2e.checkout_workflow import run_checkout_workflow

pytestmark = pytest.mark.e2e


def test_checkout_generates_invoice_and_sends_notification() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")
    run_checkout_workflow()
