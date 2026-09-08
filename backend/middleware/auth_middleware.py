"""HTTP auth middleware — /health, static assets, and SPA routes remain public."""

from __future__ import annotations

import asyncio

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware

from services.auth_service import require_http_auth

_PROTECTED_API_PREFIXES = (
    "/auth/session", "/stocks", "/scanner", "/smart-opportunities", "/market-pulse",
    "/risk", "/smart-signals", "/signals", "/journal", "/performance", "/analytics",
    "/backtest", "/production", "/universe", "/market/status", "/status", "/spx",
)


def _path_is_protected_api(path: str) -> bool:
    if path in ("/health", "/auth/login", "/internal/ws-truth"):
        return False
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _PROTECTED_API_PREFIXES)


def _is_public_request(request: Request, web_file_resolver) -> bool:
    path = request.url.path
    method = request.method.upper()
    if method == "OPTIONS" or path == "/health":
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
        if not _path_is_protected_api(path):
            return True
    return False


def _move_spx_routes_before_spa_fallback(app) -> None:
    """Ensure dynamically registered SPX API routes run before the catch-all SPA route.

    SPX is intentionally lazy-registered to avoid changing the existing application
    startup wiring. FastAPI appends included routes, so without this reorder the
    existing /{full_path:path} Flutter fallback can return index.html (HTTP 200)
    for /spx/* before the SPX router is reached.
    """
    routes = list(app.router.routes)
    spx_routes = [
        route for route in routes
        if isinstance(route, APIRoute) and route.path.startswith("/spx/")
    ]
    if not spx_routes:
        return

    spx_ids = {id(route) for route in spx_routes}
    fallback_routes = [
        route for route in routes
        if getattr(route, "path", None) == "/{full_path:path}"
    ]
    fallback_ids = {id(route) for route in fallback_routes}
    if not fallback_routes:
        return

    without_spx = [route for route in routes if id(route) not in spx_ids]
    insert_at = next(
        (index for index, route in enumerate(without_spx) if id(route) in fallback_ids),
        len(without_spx),
    )
    app.router.routes = without_spx[:insert_at] + spx_routes + without_spx[insert_at:]


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, web_file_resolver=None):
        super().__init__(app)
        self._web_file_resolver = web_file_resolver

    async def dispatch(self, request: Request, call_next) -> Response:
        if not getattr(request.app.state, "spx_router_registered", False):
            lock = getattr(request.app.state, "spx_router_lock", None)
            if lock is None:
                lock = asyncio.Lock()
                request.app.state.spx_router_lock = lock
            async with lock:
                if not getattr(request.app.state, "spx_router_registered", False):
                    from services.spx_api import router as spx_router
                    from services.spx_signal_service import spx_signal_service
                    request.app.include_router(spx_router)
                    _move_spx_routes_before_spa_fallback(request.app)
                    request.app.state.spx_router_registered = True
                    await spx_signal_service.start()

        if _is_public_request(request, self._web_file_resolver):
            return await call_next(request)
        try:
            require_http_auth(request)
        except Exception as exc:
            status_code = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", "Unauthorized")
            return JSONResponse(status_code=status_code, content={"detail": detail})
        return await call_next(request)
