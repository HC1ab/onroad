from fastapi.testclient import TestClient

from app import db
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_healthz_ok_when_db_up(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: True)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_healthz_503_when_db_down(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: False)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json()["db"] == "down"


def test_write_methods_rejected_with_error_schema():
    for method in ("post", "put", "patch", "delete"):
        r = getattr(client, method)("/api/areas")
        assert r.status_code == 405
        assert r.json() == {"error": {"code": "method_not_allowed", "message": r.json()["error"]["message"]}}


def test_unknown_path_uses_error_schema():
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
