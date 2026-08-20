"""HTTP auth middleware — /health, static assets, and SPA routes remain public."""

from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services.auth_service import require_http_auth

# REST prefixes that always require auth (WebSocket auth is handled in handlers).
_PROTECTED_API_PREFIXES = (
    "/auth/session",
    "/stocks",
    "/scanner",
    "/smart-opportunities",
    "/market-pulse",
    "/risk",
    "/smart-signals",
    "/signals",
    "/journal",
    "/performance",
    "/analytics",
    "/backtest",
    "/production",
    "/universe",
    "/market/status",
    "/status",
)


def _path_is_protected_api(path: str) -> bool:
    if path == "/health":
        return False
    if path == "/auth/login":
        return False
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in _PROTECTED_API_PREFIXES
    )


def _is_public_request(request: Request, web_file_resolver) -> bool:
    path = request.url.path
    method = request.method.upper()

    if method == "OPTIONS":
        return True
    if path == "/health":
        return True
    if path == "/auth/login" and method == "POST":
        return True
    if path in {"/docs", "/openapi.json", "/redoc"}:
        return True
    if method == "GET" and path == "/":
        return True
    if method == "GET" and web_file_resolver is not None:
        rel = path.lstrip("/")
        if web_file_resolver(rel) is not None:
            return True
        # Flutter client routes (e.g. /login) — fall back to index.html without auth.
        if not _path_is_protected_api(path):
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, web_file_resolver=None):
        super().__init__(app)
        self._web_file_resolver = web_file_resolver

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_public_request(request, self._web_file_resolver):
            return await call_next(request)
        try:
            require_http_auth(request)
        except Exception as exc:
            status_code = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", "Unauthorized")
            return JSONResponse(status_code=status_code, content={"detail": detail})
        return await call_next(request)
