"""Shared pytest fixtures — auth config for protected API routes."""

from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient

TEST_PASSWORD = "test-password-xyz"
TEST_JWT_SECRET = "pytest-jwt-secret-do-not-use-in-production"
TEST_PASSWORD_HASH = bcrypt.hashpw(TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture(autouse=True)
def _auth_config(monkeypatch):
    import services.auth_service as auth_mod

    monkeypatch.setenv("APP_PASSWORD", TEST_PASSWORD)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("APP_JWT_SECRET", TEST_JWT_SECRET)
    auth_mod._login_limiter._events.clear()


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


@pytest.fixture
def auth_headers(client) -> dict[str, str]:
    resp = client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
