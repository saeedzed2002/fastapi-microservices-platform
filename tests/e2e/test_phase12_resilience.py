"""Bounded Compose recovery proof for durable state and dependency fallbacks."""

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from platform_auth import encode_access_token
from tests.e2e.checkout_workflow import run_checkout_workflow

pytestmark = pytest.mark.e2e

LOCAL_SECRET = "local-development-jwt-secret-change-me-32-bytes"
ISSUER = "fastapi-platform.identity"
AUDIENCE = "fastapi-platform"
_ALLOWED_DISRUPTION_SERVICES = frozenset({"kafka", "rabbitmq", "redis"})


def _token(*, subject: UUID, roles: tuple[str, ...]) -> str:
    return encode_access_token(
        subject=subject,
        roles=roles,
        secret=os.environ.get("E2E_JWT_SECRET", LOCAL_SECRET),
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=900,
    )


def _require_compose_e2e() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the disposable local Compose platform")
    if os.environ.get("E2E_COMPOSE_DISRUPTION_ENABLED") == "false":
        pytest.skip("Compose lifecycle control is disabled for this E2E environment")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _compose_file() -> Path:
    configured = os.environ.get("E2E_COMPOSE_FILE")
    return (
        Path(configured)
        if configured
        else _repository_root() / "infrastructure/compose/docker-compose.yml"
    )


def _compose(*arguments: str) -> None:
    completed = subprocess.run(
        ["docker", "compose", "-f", str(_compose_file()), *arguments],
        cwd=_repository_root(),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise AssertionError(f"docker compose {' '.join(arguments)} failed: {details}")


def _stop(service: str) -> None:
    if service not in _ALLOWED_DISRUPTION_SERVICES:
        raise ValueError(f"service {service!r} is not an approved resilience-test target")
    _compose("stop", service)


def _start(service: str) -> None:
    if service not in _ALLOWED_DISRUPTION_SERVICES:
        raise ValueError(f"service {service!r} is not an approved resilience-test target")
    _compose("start", service)
    _wait_for(
        lambda: _service_is_healthy(service),
        description=f"{service} health after restart",
    )


def _wait_for(
    predicate: Callable[[], bool], *, description: str, timeout_seconds: float = 90.0
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {description}")


def _service_is_healthy(service: str) -> bool:
    completed = subprocess.run(
        ["docker", "compose", "-f", str(_compose_file()), "ps", "--format", "json", service],
        cwd=_repository_root(),
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        return False
    try:
        services = [json.loads(line) for line in completed.stdout.splitlines() if line]
    except json.JSONDecodeError:
        return False
    return (
        len(services) == 1
        and services[0].get("State") == "running"
        and services[0].get("Health") == "healthy"
    )


async def _load_order_task_intent(order_id: UUID) -> dict[str, Any] | None:
    connection = await asyncpg.connect(
        os.environ.get(
            "E2E_ORDER_DATABASE_URL",
            "postgresql://order_service:order-local-only@127.0.0.1:5432/order_service",
        )
    )
    try:
        row = await connection.fetchrow(
            """
            SELECT status, attempts, last_error
            FROM task_intents
            WHERE payload ->> 'order_id' = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            str(order_id),
        )
    finally:
        await connection.close()
    return dict(row) if row is not None else None


def test_catalog_outbox_recovers_after_kafka_outage() -> None:
    _require_compose_e2e()
    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    suffix = uuid4().hex[:12]
    query = f"phase12kafka{suffix}"
    headers = {"Authorization": f"Bearer {_token(subject=uuid4(), roles=('admin',))}"}

    with httpx.Client(timeout=10.0, verify=False) as client:
        _stop("kafka")
        try:
            product = client.post(
                f"{base_url}/api/v1/catalog/products",
                headers=headers,
                json={
                    "name": query,
                    "slug": f"phase-12-kafka-{suffix}",
                    "description": "Kafka recovery E2E test",
                    "price_amount": "12.50",
                    "currency": "USD",
                    "attributes": {},
                },
            )
            product.raise_for_status()
            product_id = product.json()["id"]
            published = client.post(
                f"{base_url}/api/v1/catalog/products/{product_id}/publish", headers=headers
            )
            published.raise_for_status()
            assert published.json()["status"] == "published"
        finally:
            _start("kafka")

        def product_reaches_search() -> bool:
            response = client.get(f"{base_url}/api/v1/search/products", params={"q": query})
            if response.status_code != 200:
                return False
            matches = [
                item for item in response.json()["items"] if item["product_id"] == product_id
            ]
            return len(matches) == 1

        _wait_for(
            product_reaches_search, description="Catalog outbox publication after Kafka recovery"
        )


def test_cart_uses_postgresql_during_redis_outage() -> None:
    _require_compose_e2e()
    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    customer_id, variant_id = uuid4(), uuid4()
    headers = {"Authorization": f"Bearer {_token(subject=customer_id, roles=('customer',))}"}

    with httpx.Client(timeout=10.0, verify=False) as client:
        client.get(f"{base_url}/api/v1/carts/me", headers=headers).raise_for_status()
        _stop("redis")
        try:
            updated = client.post(
                f"{base_url}/api/v1/carts/me/items",
                headers=headers,
                json={"variant_id": str(variant_id), "quantity": 2},
            )
            updated.raise_for_status()
            assert [(item["variant_id"], item["quantity"]) for item in updated.json()["items"]] == [
                (str(variant_id), 2)
            ]
            persisted = client.get(f"{base_url}/api/v1/carts/me", headers=headers)
            persisted.raise_for_status()
            assert [
                (item["variant_id"], item["quantity"]) for item in persisted.json()["items"]
            ] == [(str(variant_id), 2)]
        finally:
            _start("redis")

        _wait_for(
            lambda: client.get(f"{base_url}/api/v1/carts/me", headers=headers).status_code == 200,
            description="Cart recovery after Redis restart",
        )


def test_order_task_intent_recovers_after_rabbitmq_outage() -> None:
    _require_compose_e2e()
    rabbitmq_started = False

    def restore_broker_after_durable_failure(order_id: UUID) -> None:
        nonlocal rabbitmq_started

        def dispatch_failure_is_persisted() -> bool:
            task_intent = asyncio.run(_load_order_task_intent(order_id))
            return bool(
                task_intent
                and task_intent["status"] == "PENDING"
                and task_intent["attempts"] >= 1
                and task_intent["last_error"]
            )

        _wait_for(
            dispatch_failure_is_persisted,
            description="durable Order task-intent dispatch failure",
        )
        _start("rabbitmq")
        rabbitmq_started = True

    _stop("rabbitmq")
    try:
        result = run_checkout_workflow(before_invoice_wait=restore_broker_after_durable_failure)
    finally:
        if not rabbitmq_started:
            _start("rabbitmq")

    assert result.new_mail_messages == 1
