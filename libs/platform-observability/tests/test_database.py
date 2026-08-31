from sqlalchemy import create_engine, text

from platform_observability import metrics_response
from platform_observability.database import instrument_engine


def test_database_instrumentation_uses_bounded_operation_labels() -> None:
    engine = create_engine("sqlite://")
    instrument_engine(engine, service_name="database-test-service")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    metrics = metrics_response().body.decode()
    assert 'service="database-test-service"' in metrics
    assert 'operation="select"' in metrics
    assert "SELECT 1" not in metrics
