"""JWT access token authentication."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field

import config

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class _RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._events[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again later.",
            )
        bucket.append(now)


_login_limiter = _RateLimiter(config.AUTH_RATE_LIMIT, config.AUTH_RATE_WINDOW_SECONDS)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def verify_password(plain_password: str) -> bool:
    password_hash = config.get_app_password_hash()
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token() -> tuple[str, int]:
    secret = config.get_app_jwt_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    expires_in = config.JWT_ACCESS_TOKEN_MINUTES * 60
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": "app_user",
        "iat": datetime.now(timezone.utc),
        "exp": exp,
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    secret = config.get_app_jwt_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def login(request: Request, body: LoginRequest) -> LoginResponse:
    _login_limiter.check(_client_key(request))
    if not verify_password(body.password):
        logger.info("Failed login attempt from %s", _client_key(request))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token, expires_in = create_access_token()
    return LoginResponse(access_token=token, expires_in=expires_in)


def extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    return token or None


def require_http_auth(request: Request) -> None:
    token = extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    decode_access_token(token)


async def require_ws_auth(ws, timeout: float = 10.0) -> bool:
    """First client message must be {\"type\":\"auth\",\"token\":\"...\"}."""
    import asyncio
    import json

    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
        msg = json.loads(raw)
    except Exception:
        await ws.close(code=4401)
        return False
    if msg.get("type") != "auth" or not msg.get("token"):
        await ws.close(code=4401)
        return False
    try:
        decode_access_token(str(msg["token"]))
        return True
    except HTTPException:
        await ws.close(code=4401)
        return False
