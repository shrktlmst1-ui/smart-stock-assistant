"""Authentication tests — login, rate limit, JWT, REST/WS protection."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_JWT_SECRET, TEST_PASSWORD


def test_login_success(client: TestClient):
    resp = client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert "SmartStock" not in resp.text


def test_login_failure(client: TestClient):
    resp = client.post("/auth/login", json={"password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_login_rate_limit(client: TestClient, monkeypatch):
    import services.auth_service as auth_mod

    auth_mod._login_limiter._events.clear()
    auth_mod._login_limiter.limit = 3
    auth_mod._login_limiter.window = 60
    for _ in range(3):
        client.post("/auth/login", json={"password": "wrong-password"})
    resp = client.post("/auth/login", json={"password": "wrong-password"})
    assert resp.status_code == 429


def test_protected_route_requires_auth(client: TestClient):
    resp = client.get("/stocks/opportunities")
    assert resp.status_code == 401


def test_protected_route_with_valid_token(client: TestClient, auth_headers: dict):
    resp = client.get("/stocks/opportunities", headers=auth_headers)
    assert resp.status_code == 200


def test_health_public_without_auth(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_expired_token_rejected(client: TestClient, monkeypatch):
    expired = jwt.encode(
        {"sub": "app_user", "exp": int(time.time()) - 60},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    resp = client.get(
        "/market-pulse",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


def test_forged_token_rejected(client: TestClient):
    forged = jwt.encode(
        {"sub": "app_user", "exp": int(time.time()) + 3600},
        "wrong-secret",
        algorithm="HS256",
    )
    resp = client.get(
        "/market-pulse",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert resp.status_code == 401


def test_invalid_token_returns_401_when_jwt_secret_missing(client: TestClient, monkeypatch):
    monkeypatch.delenv("APP_JWT_SECRET", raising=False)
    resp = client.get(
        "/stocks/opportunities?limit=20",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired token"


def test_login_returns_503_when_jwt_secret_missing(client: TestClient, monkeypatch):
    monkeypatch.delenv("APP_JWT_SECRET", raising=False)
    resp = client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Authentication is not configured"


def test_login_then_opportunities_returns_200(client: TestClient):
    login = client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert login.status_code == 200
    token = login.json()["access_token"]
    opp = client.get(
        "/stocks/opportunities?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert opp.status_code == 200


def test_websocket_requires_auth(client: TestClient, auth_headers: dict):
    token = auth_headers["Authorization"].split(" ", 1)[1]
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_text()

    with client.websocket_connect("/ws/market-pulse") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "pulse_health"


def test_spa_client_route_public_without_auth(client: TestClient, auth_headers: dict, tmp_path, monkeypatch):
    """Flutter deep links must not require JWT before index.html is served."""
    import main as main_mod

    index = tmp_path / "index.html"
    index.write_text("<html><body>app</body></html>", encoding="utf-8")

    def resolver(rel: str):
        if rel == "index.html" or rel == "":
            return index
        return None

    monkeypatch.setattr(main_mod, "WEB_ROOT", tmp_path)
    monkeypatch.setattr(main_mod, "INDEX_HTML", index)
    monkeypatch.setattr(main_mod, "_web_build_available", lambda: True)

    resp = client.get("/login")
    assert resp.status_code == 200
    assert "app" in resp.text


def test_websocket_rejects_invalid_token(client: TestClient):
    with client.websocket_connect("/ws/market-pulse") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": "not-a-valid-token"}))
        with pytest.raises(Exception):
            ws.receive_text()


WEB_ORIGIN = "https://smart-stock-assistant-web.onrender.com"


def test_cors_on_login_and_opportunities(client: TestClient, auth_headers: dict):
    login = client.post(
        "/auth/login",
        json={"password": TEST_PASSWORD},
        headers={"Origin": WEB_ORIGIN},
    )
    assert login.status_code == 200
    assert login.headers.get("access-control-allow-origin") == WEB_ORIGIN

    token = login.json()["access_token"]
    opp = client.get(
        "/stocks/opportunities?limit=20",
        headers={
            "Origin": WEB_ORIGIN,
            "Authorization": f"Bearer {token}",
        },
    )
    assert opp.status_code == 200
    assert opp.headers.get("access-control-allow-origin") == WEB_ORIGIN


def test_cors_on_unauthorized_opportunities(client: TestClient):
    resp = client.get(
        "/stocks/opportunities?limit=20",
        headers={"Origin": WEB_ORIGIN},
    )
    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") == WEB_ORIGIN


def test_cors_preflight_opportunities(client: TestClient):
    resp = client.options(
        "/stocks/opportunities",
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == WEB_ORIGIN
    assert "authorization" in resp.headers.get("access-control-allow-headers", "").lower()
