from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_v05a_status():
    with TestClient(app) as client:
        response = client.get("/api/v05a/status")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "0.5A"
    assert body["event_model"] == "Inbox + Transactional Outbox"


def test_inbox_idempotency():
    event_id = f"pytest-{uuid4()}"
    payload = {
        "provider": "TEST",
        "event_type": "ORDER_CHANGED",
        "external_event_id": event_id,
        "signature_status": "VERIFIED",
        "payload": {"order_id": "demo-1"},
    }
    with TestClient(app) as client:
        first = client.post("/api/v05a/events/inbox", json=payload)
        second = client.post("/api/v05a/events/inbox", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["id"] == second.json()["id"]


def test_transactional_outbox_api():
    unique = str(uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/api/v05a/events/outbox",
            json={
                "aggregate_type": "ORDER",
                "aggregate_id": unique,
                "event_type": "ORDER_IMPORTED",
                "payload": {"source": "pytest"},
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
