"""Application configuration — Polygon/Massive Stocks Developer plan."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load backend/.env only (never .env.example)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

def get_polygon_api_key() -> str:
    """Load Polygon/Massive API key from environment (Render, .env, or shell)."""
    return (os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY") or "").strip()


# API key: MASSIVE_API_KEY or POLYGON_API_KEY from backend/.env / Render env
POLYGON_API_KEY: str = get_polygon_api_key()

POLYGON_PLAN: Literal["free", "starter", "developer", "advanced"] = os.getenv(
    "POLYGON_PLAN", "developer"
)

PLAN_RATE_LIMITS = {
    "free": 5,
    "starter": 100,
    "developer": 500,
    "advanced": 1000,
}

PLAN_POLL_INTERVALS = {
    "free": 15,
    "starter": 5,
    "developer": 1,
    "advanced": 1,
}

PLAN_WEBSOCKET_ENABLED = {
    "free": False,
    "starter": True,
    "developer": True,
    "advanced": True,
}

RATE_LIMIT_PER_MINUTE: int = PLAN_RATE_LIMITS.get(POLYGON_PLAN, 500)
POLL_INTERVAL_SECONDS: int = int(
    os.getenv("POLL_INTERVAL_SECONDS", str(os.getenv("SCANNER_TICK_SECONDS", "15")))
)
WEBSOCKET_ENABLED: bool = os.getenv(
    "WEBSOCKET_ENABLED", str(PLAN_WEBSOCKET_ENABLED.get(POLYGON_PLAN, True))
).lower() == "true"

DEFAULT_SYMBOLS: list[str] = [
    s.strip().upper()
    for s in os.getenv("WATCHLIST", "").split(",")
    if s.strip()
]

# US Market Scanner (Phase 2/3 — Institutional AI Scanner)
SCANNER_TICK_SECONDS: int = int(os.getenv("SCANNER_TICK_SECONDS", "15"))
SCANNER_UNIVERSE_REFRESH_SECONDS: int = int(os.getenv("SCANNER_UNIVERSE_REFRESH_SECONDS", "60"))
SCANNER_TOP_N: int = int(os.getenv("SCANNER_TOP_N", "20"))
SCANNER_DEEP_POOL: int = int(os.getenv("SCANNER_DEEP_POOL", "200"))
SCANNER_CANDIDATE_POOL: int = int(os.getenv("SCANNER_CANDIDATE_POOL", "60"))
SCANNER_WORKER_THREADS: int = int(os.getenv("SCANNER_WORKER_THREADS", "8"))
UNIVERSE_CACHE_SECONDS: int = int(os.getenv("UNIVERSE_CACHE_SECONDS", "86400"))
SCANNER_MIN_DAY_VOLUME: int = int(os.getenv("SCANNER_MIN_DAY_VOLUME", "250000"))
SCANNER_MIN_AVG_VOLUME: int = int(os.getenv("SCANNER_MIN_AVG_VOLUME", "200000"))
SCANNER_MIN_PRICE: float = float(os.getenv("SCANNER_MIN_PRICE", "0.01"))
SCANNER_MAX_PRICE: float = float(os.getenv("SCANNER_MAX_PRICE", "10.0"))
SCANNER_RANK_POOL: int = int(os.getenv("SCANNER_RANK_POOL", "400"))
SCANNER_DEEP_BATCH: int = int(os.getenv("SCANNER_DEEP_BATCH", "40"))
SCANNER_MIN_RVOL: float = float(os.getenv("SCANNER_MIN_RVOL", "1.2"))
SCANNER_MAX_SPREAD_PCT: float = float(os.getenv("SCANNER_MAX_SPREAD_PCT", "2.0"))
SCANNER_MIN_MARKET_CAP: float = float(os.getenv("SCANNER_MIN_MARKET_CAP", "50000000"))
SCANNER_BOARD_SIZE: int = int(os.getenv("SCANNER_BOARD_SIZE", "20"))

POLYGON_BASE_URL: str = "https://api.polygon.io"
POLYGON_WS_URL: str = "wss://socket.polygon.io/stocks"

# Production + local dev origins for cross-origin Flutter web.
REQUIRED_CORS_ORIGINS: tuple[str, ...] = (
    "https://smart-stock-assistant-web.onrender.com",
    "https://smart-stock-assistant.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        ",".join(REQUIRED_CORS_ORIGINS),
    ).split(",")
    if o.strip()
]


def get_cors_origins() -> list[str]:
    """Merge env-configured origins with required production/dev origins."""
    origins: list[str] = list(REQUIRED_CORS_ORIGINS)
    for origin in CORS_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    return origins

# Bar refresh intervals (seconds) to stay within rate limits
MINUTE_BARS_REFRESH_SECONDS: int = int(os.getenv("MINUTE_BARS_REFRESH_SECONDS", "60"))
DAILY_BARS_REFRESH_SECONDS: int = int(os.getenv("DAILY_BARS_REFRESH_SECONDS", "3600"))
NEWS_REFRESH_SECONDS: int = int(os.getenv("NEWS_REFRESH_SECONDS", "120"))

# Benzinga News API (optional)
BENZINGA_API_KEY: str = os.getenv("BENZINGA_API_KEY", "")
BENZINGA_ENABLED: bool = os.getenv("BENZINGA_ENABLED", "false").lower() == "true"

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

# Risk / account defaults for position sizing
ACCOUNT_SIZE: float = float(os.getenv("ACCOUNT_SIZE", "100000"))
RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
NOTIFICATION_MIN_CONFIDENCE: float = float(os.getenv("NOTIFICATION_MIN_CONFIDENCE", "80"))
MIN_CONFIDENCE_PRODUCTION: float = float(os.getenv("MIN_CONFIDENCE_PRODUCTION", "85"))
MIN_RISK_REWARD: float = float(os.getenv("MIN_RISK_REWARD", "2.5"))

# Smart Opportunity Scanner (الفرص الذكية)
SMART_SCANNER_TOP_N: int = int(os.getenv("SMART_SCANNER_TOP_N", "5"))
SMART_SCANNER_MIN_RVOL: float = float(os.getenv("SMART_SCANNER_MIN_RVOL", "1.5"))
SMART_SCANNER_MIN_AI_SCORE: float = float(os.getenv("SMART_SCANNER_MIN_AI_SCORE", "65"))
SMART_SCANNER_MAX_SPREAD_PCT: float = float(os.getenv("SMART_SCANNER_MAX_SPREAD_PCT", "0.5"))
SMART_SCANNER_MIN_DAY_VOLUME: int = int(os.getenv("SMART_SCANNER_MIN_DAY_VOLUME", "500000"))
SMART_SCANNER_DEEP_POOL: int = int(os.getenv("SMART_SCANNER_DEEP_POOL", "40"))

# Entry decision thresholds (قرار الدخول)
ENTRY_MIN_AI_SCORE: float = float(os.getenv("ENTRY_MIN_AI_SCORE", "80"))
ENTRY_MIN_RRR: float = float(os.getenv("ENTRY_MIN_RRR", "2.0"))
ENTRY_MAX_SPREAD_PCT: float = float(os.getenv("ENTRY_MAX_SPREAD_PCT", "0.5"))
ENTRY_MIN_RVOL: float = float(os.getenv("ENTRY_MIN_RVOL", "1.5"))
ENTRY_MIN_DAY_VOLUME: int = int(os.getenv("ENTRY_MIN_DAY_VOLUME", "500000"))
ENTRY_SIGNAL_EXPIRY_CANDLES: int = int(os.getenv("ENTRY_SIGNAL_EXPIRY_CANDLES", "3"))
ENTRY_TIMEFRAME_MINUTES: int = int(os.getenv("ENTRY_TIMEFRAME_MINUTES", "15"))
ENTRY_DATA_MAX_AGE_SECONDS: int = int(os.getenv("ENTRY_DATA_MAX_AGE_SECONDS", "120"))

# Risk calculator defaults (حاسبة المخاطرة)
DEFAULT_ACCOUNT_SIZE: float = float(os.getenv("DEFAULT_ACCOUNT_SIZE", "100000"))
DEFAULT_RISK_PCT: float = float(os.getenv("DEFAULT_RISK_PCT", "0.5"))

# Market Pulse — نبض السوق الذكي (Phase 1, disabled by default)
MARKET_PULSE_ENABLED: bool = os.getenv("MARKET_PULSE_ENABLED", "false").lower() == "true"
MASSIVE_WS_URL: str = os.getenv("MASSIVE_WS_URL", "wss://socket.massive.com/stocks")
MARKET_PULSE_MAX_SYMBOLS: int = int(os.getenv("MARKET_PULSE_MAX_SYMBOLS", "50"))
MARKET_PULSE_SYMBOL_TTL_SECONDS: int = int(os.getenv("MARKET_PULSE_SYMBOL_TTL_SECONDS", "3600"))
MARKET_PULSE_ENTER_MIN_SCORE: float = float(os.getenv("MARKET_PULSE_ENTER_MIN_SCORE", "85"))
MARKET_PULSE_WAIT_MIN_SCORE: float = float(os.getenv("MARKET_PULSE_WAIT_MIN_SCORE", "65"))
MARKET_PULSE_MAX_SPREAD_BPS: float = float(os.getenv("MARKET_PULSE_MAX_SPREAD_BPS", "50"))
MARKET_PULSE_DATA_MAX_AGE_SECONDS: int = int(os.getenv("MARKET_PULSE_DATA_MAX_AGE_SECONDS", "120"))
MARKET_PULSE_ALERT_TTL_SECONDS: int = int(os.getenv("MARKET_PULSE_ALERT_TTL_SECONDS", "900"))
MARKET_PULSE_WS_BACKOFF_BASE: float = float(os.getenv("MARKET_PULSE_WS_BACKOFF_BASE_SECONDS", "2"))
MARKET_PULSE_WS_BACKOFF_MAX: float = float(os.getenv("MARKET_PULSE_WS_BACKOFF_MAX_SECONDS", "60"))
MARKET_PULSE_NEWS_POLL_SECONDS: int = int(os.getenv("MARKET_PULSE_NEWS_POLL_SECONDS", "60"))
MARKET_PULSE_BROADCAST_INTERVAL_SECONDS: float = float(
    os.getenv("MARKET_PULSE_BROADCAST_INTERVAL_SECONDS", "5")
)
MARKET_PULSE_WS_MAX_CLIENTS: int = int(os.getenv("MARKET_PULSE_WS_MAX_CLIENTS", "50"))
MARKET_PULSE_FIXTURE_MODE: bool = os.getenv("MARKET_PULSE_FIXTURE_MODE", "false").lower() == "true"

# App authentication (JWT — secrets from env only)
APP_PASSWORD: str = os.getenv("APP_PASSWORD", "").strip()
APP_PASSWORD_HASH: str = os.getenv("APP_PASSWORD_HASH", "").strip()
APP_JWT_SECRET: str = os.getenv("APP_JWT_SECRET", "").strip()
JWT_ACCESS_TOKEN_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "480"))
AUTH_RATE_LIMIT: int = int(os.getenv("AUTH_RATE_LIMIT", "5"))
AUTH_RATE_WINDOW_SECONDS: int = int(os.getenv("AUTH_RATE_WINDOW_SECONDS", "60"))


def get_app_password() -> str:
    """Plain login password from env (optional — compared in memory with timing-safe digest)."""
    return os.getenv("APP_PASSWORD", APP_PASSWORD).strip()


def get_app_password_hash() -> str:
    """Optional bcrypt hash — when unset, login falls back to APP_PASSWORD."""
    return os.getenv("APP_PASSWORD_HASH", APP_PASSWORD_HASH).strip()


def get_app_jwt_secret() -> str:
    """Read JWT secret at call time from os.environ only — no module-level fallback."""
    raw = os.environ.get("APP_JWT_SECRET")
    if raw is None:
        return ""
    return raw.strip()


def is_auth_password_configured() -> bool:
    return bool(get_app_password_hash() or get_app_password())


def is_auth_jwt_configured() -> bool:
    return bool(get_app_jwt_secret())


def is_auth_fully_configured() -> bool:
    return is_auth_password_configured() and is_auth_jwt_configured()


def is_pytest_running() -> bool:
    import sys
    return "pytest" in sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST"))


def is_production_release() -> bool:
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "")).lower()
    return (
        os.getenv("RENDER", "").lower() == "true"
        or env in ("production", "release", "prod")
        or os.getenv("FLUTTER_RELEASE", "").lower() == "true"
    )


def is_market_pulse_fixture_allowed() -> bool:
    """Fixture data is dev/test only — blocked in production/release."""
    if not MARKET_PULSE_FIXTURE_MODE:
        return False
    if is_production_release():
        return False
    return True
