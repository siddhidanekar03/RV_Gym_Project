from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend.app.core.database import get_db
from backend.app.main import app


def test_health_endpoint_healthy(client: TestClient):
    """Verify /api/health reports healthy system and connected database status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "healthy"
    assert data["environment"] == "test"
    assert data["database"]["status"] == "connected"
    assert data["database"]["latency_ms"] >= 0.0
    assert "timestamp" in data


def test_health_endpoint_degraded_on_db_failure():
    """Verify /api/health reports HTTP 503 when database connectivity fails."""
    broken_session = MagicMock()
    broken_session.execute.side_effect = RuntimeError("Database connection timed out")

    def override_broken_db():
        yield broken_session

    app.dependency_overrides[get_db] = override_broken_db
    try:
        with TestClient(app) as client:
            res = client.get("/api/health")
            assert res.status_code == 503
            data = res.json()
            assert data["status"] == "unhealthy"
            assert data["database"]["status"] == "disconnected"
    finally:
        app.dependency_overrides.clear()
