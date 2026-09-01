from pathlib import Path

SERVICES = (
    "reference-service",
    "identity-service",
    "customer-service",
    "catalog-service",
    "search-service",
    "media-service",
    "inventory-service",
    "cart-service",
    "order-service",
    "payment-service",
    "notification-service",
    "chat-service",
    "shipping-service",
)

RUNTIME_PIP_PRUNING = (
    "RUN rm -rf /usr/local/lib/python3.14/site-packages/pip "
    "/usr/local/lib/python3.14/site-packages/pip-*.dist-info "
    "/usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14 \\\n"
    "    && useradd --create-home --uid 10001 appuser"
)


def test_runtime_images_exclude_global_pip_and_vendored_build_packages() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    for service in SERVICES:
        dockerfile = (repository_root / "services" / service / "Dockerfile").read_text(
            encoding="utf-8"
        )

        assert RUNTIME_PIP_PRUNING in dockerfile
        assert dockerfile.index("COPY --from=builder /app/.venv ./.venv") < dockerfile.index(
            RUNTIME_PIP_PRUNING
        )
        assert dockerfile.index(RUNTIME_PIP_PRUNING) < dockerfile.index("USER appuser")
