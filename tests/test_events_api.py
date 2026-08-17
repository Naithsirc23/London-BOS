from datetime import datetime, timezone

from fastapi.testclient import TestClient

from londonbos_core.storage import init_db, record_event


def test_event_storage_and_api(tmp_path, monkeypatch):
    db = tmp_path / "events.sqlite"
    init_db(db)
    event_id = record_event(
        db,
        "BREAKOUT_DETECTED",
        timestamp=datetime(2026, 8, 17, 7, 20, tzinfo=timezone.utc),
        session_date="2026-08-17",
        direction="BUY",
        price=1.1052,
        r_multiple=0.25,
        source="paper_trade",
        metadata={"window_minutes": 20, "operable": True},
    )
    assert event_id == 1

    monkeypatch.setenv("LONDONBOS_DB", str(db))
    import api
    api.DB_PATH = db
    client = TestClient(api.app)

    health = client.get("/api/health").json()
    assert health["mode"] == "read_only"
    assert "trade_events" in health["tables"]

    response = client.get("/api/events?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["data"][0]["id"] == 1
    assert payload["data"][0]["metadata"]["window_minutes"] == 20
    assert payload["freshness"]["source"] == "sqlite"
