"""Application configuration — Polygon/Massive Stocks Developer plan."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load backend/.env only (never .env.example)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# API key: MASSIVE_API_KEY or POLYGON_API_KEY from backend/.env
POLYGON_API_KEY: str = os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY") or ""

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
SCANNER_DEEP_POOL: int = int(os.getenv("SCANNER_DEEP_POOL", "100"))
SCANNER_CANDIDATE_POOL: int = int(os.getenv("SCANNER_CANDIDATE_POOL", "60"))
SCANNER_WORKER_THREADS: int = int(os.getenv("SCANNER_WORKER_THREADS", "8"))
UNIVERSE_CACHE_SECONDS: int = int(os.getenv("UNIVERSE_CACHE_SECONDS", "86400"))
SCANNER_MIN_DAY_VOLUME: int = int(os.getenv("SCANNER_MIN_DAY_VOLUME", "250000"))
SCANNER_MIN_AVG_VOLUME: int = int(os.getenv("SCANNER_MIN_AVG_VOLUME", "200000"))
SCANNER_MIN_PRICE: float = float(os.getenv("SCANNER_MIN_PRICE", "2.0"))
SCANNER_MAX_PRICE: float = float(os.getenv("SCANNER_MAX_PRICE", "500.0"))
SCANNER_MIN_RVOL: float = float(os.getenv("SCANNER_MIN_RVOL", "1.2"))
SCANNER_MAX_SPREAD_PCT: float = float(os.getenv("SCANNER_MAX_SPREAD_PCT", "2.0"))
SCANNER_MIN_MARKET_CAP: float = float(os.getenv("SCANNER_MIN_MARKET_CAP", "50000000"))
SCANNER_BOARD_SIZE: int = int(os.getenv("SCANNER_BOARD_SIZE", "20"))

POLYGON_BASE_URL: str = "https://api.polygon.io"
POLYGON_WS_URL: str = "wss://socket.polygon.io/stocks"

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

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
