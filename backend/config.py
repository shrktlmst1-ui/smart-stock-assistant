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

# Stocks WebSocket hub — batched subscriptions (avoids Polygon 1008 policy violations)
WS_MAX_CONNECTIONS: int = int(os.getenv("WS_MAX_CONNECTIONS", "1"))
WS_SYMBOLS_PER_SHARD: int = int(os.getenv("WS_SYMBOLS_PER_SHARD", "60"))
WS_CHANNELS_PER_SUBSCRIBE_BATCH: int = int(os.getenv("WS_CHANNELS_PER_SUBSCRIBE_BATCH", "40"))
WS_SUBSCRIBE_BATCH_DELAY_SEC: float = float(os.getenv("WS_SUBSCRIBE_BATCH_DELAY_SEC", "0.35"))
WS_RESYNC_SECONDS: float = float(os.getenv("WS_RESYNC_SECONDS", "12"))
WS_RECV_TIMEOUT_SECONDS: float = float(os.getenv("WS_RECV_TIMEOUT_SECONDS", "3"))

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
POLYGON_WS_URL: str = os.getenv("POLYGON_WS_URL", "wss://socket.massive.com/stocks")

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

# Pre-Move Predictor — early setup detection (weights sum to 100)
PREMOVE_ENABLED: bool = os.getenv("PREMOVE_ENABLED", "true").lower() == "true"
PREMOVE_FAST_SCAN_LIMIT: int = int(os.getenv("PREMOVE_FAST_SCAN_LIMIT", "3000"))
PREMOVE_CANDIDATE_LIMIT: int = int(os.getenv("PREMOVE_CANDIDATE_LIMIT", "120"))
PREMOVE_DEEP_LIMIT: int = int(os.getenv("PREMOVE_DEEP_LIMIT", "72"))
PREMOVE_MIN_SCORE_DISPLAY: int = int(os.getenv("PREMOVE_MIN_SCORE_DISPLAY", "60"))
PREMOVE_DATA_MAX_AGE_SECONDS: int = int(os.getenv("PREMOVE_DATA_MAX_AGE_SECONDS", "120"))
PREMOVE_WEIGHT_EARLY_ACTIVITY: float = float(os.getenv("PREMOVE_WEIGHT_EARLY_ACTIVITY", "28"))
PREMOVE_WEIGHT_VOLUME: float = float(os.getenv("PREMOVE_WEIGHT_VOLUME", "12"))
PREMOVE_WEIGHT_STRUCTURE: float = float(os.getenv("PREMOVE_WEIGHT_STRUCTURE", "10"))
PREMOVE_WEIGHT_VWAP: float = float(os.getenv("PREMOVE_WEIGHT_VWAP", "10"))
PREMOVE_WEIGHT_BREAKOUT: float = float(os.getenv("PREMOVE_WEIGHT_BREAKOUT", "10"))
PREMOVE_WEIGHT_NEWS: float = float(os.getenv("PREMOVE_WEIGHT_NEWS", "10"))
PREMOVE_WEIGHT_LIQUIDITY: float = float(os.getenv("PREMOVE_WEIGHT_LIQUIDITY", "10"))
PREMOVE_CONFLUENCE_BONUS_MAX: float = float(os.getenv("PREMOVE_CONFLUENCE_BONUS_MAX", "5"))
PREMOVE_VOL_ACCEL_STRONG: float = float(os.getenv("PREMOVE_VOL_ACCEL_STRONG", "1.5"))
PREMOVE_EARLY_RVOL_ST_STRONG: float = float(os.getenv("PREMOVE_EARLY_RVOL_ST_STRONG", "2.0"))
PREMOVE_SIGNAL_DECAY_START_MIN: float = float(os.getenv("PREMOVE_SIGNAL_DECAY_START_MIN", "5"))
PREMOVE_SIGNAL_DECAY_PER_MIN: float = float(os.getenv("PREMOVE_SIGNAL_DECAY_PER_MIN", "1.5"))
PREMOVE_MIN_ANALYSIS_BARS: int = int(os.getenv("PREMOVE_MIN_ANALYSIS_BARS", "4"))
PREMOVE_MIN_LIQUIDITY_SCORE: float = float(os.getenv("PREMOVE_MIN_LIQUIDITY_SCORE", "40"))
PREMOVE_MIN_RRR: float = float(os.getenv("PREMOVE_MIN_RRR", "1.2"))
PREMOVE_LATE_RSI: float = float(os.getenv("PREMOVE_LATE_RSI", "85"))
PREMOVE_LATE_EXTENSION_PCT: float = float(os.getenv("PREMOVE_LATE_EXTENSION_PCT", "18"))
PREMOVE_BAR_CACHE_TTL: int = int(os.getenv("PREMOVE_BAR_CACHE_TTL", "60"))
PREMOVE_BAR_CACHE_MAX: int = int(os.getenv("PREMOVE_BAR_CACHE_MAX", "200"))

# Jump Alert Registry — sticky alerts independent of scan snapshot
JUMP_ALERT_TTL_SECONDS: int = int(os.getenv("JUMP_ALERT_TTL_SECONDS", "1800"))
JUMP_ALERT_DISPLAY_LIMIT: int = int(os.getenv("JUMP_ALERT_DISPLAY_LIMIT", "3"))

# API snapshot cache + memory bounds (performance only — no signal logic)
SYMBOL_CACHE_MAX_ENTRIES: int = int(os.getenv("SYMBOL_CACHE_MAX_ENTRIES", "400"))
TICKER_META_CACHE_MAX_ENTRIES: int = int(os.getenv("TICKER_META_CACHE_MAX_ENTRIES", "2000"))
PER_SYMBOL_PREP_TIMEOUT_SEC: float = float(os.getenv("PER_SYMBOL_PREP_TIMEOUT_SEC", "20"))

# Stage Progression Engine — evidence-based lifecycle (symbol-agnostic)
STAGE_HISTORY_MAX: int = int(os.getenv("STAGE_HISTORY_MAX", "8"))
STAGE_STATE_TTL_SECONDS: int = int(os.getenv("STAGE_STATE_TTL_SECONDS", "7200"))
STAGE_EW_MIN_PROGRESSION: float = float(os.getenv("STAGE_EW_MIN_PROGRESSION", "32"))
STAGE_PB_MIN_PROGRESSION: float = float(os.getenv("STAGE_PB_MIN_PROGRESSION", "48"))
STAGE_EE_MIN_PROGRESSION: float = float(os.getenv("STAGE_EE_MIN_PROGRESSION", "62"))
STAGE_HC_MIN_PROGRESSION: float = float(os.getenv("STAGE_HC_MIN_PROGRESSION", "78"))
STAGE_PERSISTENCE_2M: int = int(os.getenv("STAGE_PERSISTENCE_2M", "2"))
STAGE_PERSISTENCE_3M: int = int(os.getenv("STAGE_PERSISTENCE_3M", "3"))
STAGE_PERSISTENCE_5M: int = int(os.getenv("STAGE_PERSISTENCE_5M", "5"))
STAGE_DECAY_START_MIN: float = float(os.getenv("STAGE_DECAY_START_MIN", "6"))
STAGE_DECAY_PER_MIN: float = float(os.getenv("STAGE_DECAY_PER_MIN", "2.0"))
STAGE_STALE_WATCH_MIN: float = float(os.getenv("STAGE_STALE_WATCH_MIN", "10"))
STAGE_RESISTANCE_NEAR_PCT: float = float(os.getenv("STAGE_RESISTANCE_NEAR_PCT", "8.0"))
STAGE_RESISTANCE_CLOSE_PCT: float = float(os.getenv("STAGE_RESISTANCE_CLOSE_PCT", "4.0"))
STAGE_BREAKOUT_NEAR_PCT: float = float(os.getenv("STAGE_BREAKOUT_NEAR_PCT", "2.5"))
STAGE_VOL_ACCEL_MIN: float = float(os.getenv("STAGE_VOL_ACCEL_MIN", "1.15"))
STAGE_VOL_ACCEL_STRONG: float = float(os.getenv("STAGE_VOL_ACCEL_STRONG", "1.25"))
STAGE_RVOL_MIN: float = float(os.getenv("STAGE_RVOL_MIN", "1.4"))
STAGE_REGRESSION_DROP: float = float(os.getenv("STAGE_REGRESSION_DROP", "18"))

# EARLY_ENTRY Gate — precision-focused (symbol-agnostic)
STAGE_EE_MIN_TRIGGER_READINESS: float = float(os.getenv("STAGE_EE_MIN_TRIGGER_READINESS", "65"))
STAGE_EE_PB_PERSISTENCE_MIN: int = int(os.getenv("STAGE_EE_PB_PERSISTENCE_MIN", "2"))
STAGE_EE_MOMENTUM_PERSISTENCE_MIN: int = int(os.getenv("STAGE_EE_MOMENTUM_PERSISTENCE_MIN", "2"))
STAGE_EE_MAX_EXTENSION_PCT: float = float(os.getenv("STAGE_EE_MAX_EXTENSION_PCT", "14"))
STAGE_EE_MAX_RESISTANCE_DIST_PCT: float = float(os.getenv("STAGE_EE_MAX_RESISTANCE_DIST_PCT", "2.5"))
STAGE_EE_MIN_PRICE_HOLDING: float = float(os.getenv("STAGE_EE_MIN_PRICE_HOLDING", "52"))
STAGE_EE_MIN_RVOL: float = float(os.getenv("STAGE_EE_MIN_RVOL", "1.3"))
STAGE_EE_MAX_SPREAD_PCT: float = float(os.getenv("STAGE_EE_MAX_SPREAD_PCT", "3.0"))

# REAL_JUMP wave lifecycle — symbol-agnostic, tunable via env
REAL_JUMP_REARM_MIN_MINUTES: float = float(os.getenv("REAL_JUMP_REARM_MIN_MINUTES", "8"))
REAL_JUMP_REARM_MIN_EXPANSION_PCT: float = float(os.getenv("REAL_JUMP_REARM_MIN_EXPANSION_PCT", "5.0"))
REAL_JUMP_WAVE_END_SIGNALS_REQUIRED: int = int(os.getenv("REAL_JUMP_WAVE_END_SIGNALS_REQUIRED", "3"))
REAL_JUMP_WAVE_END_CONFIRM_TICKS: int = int(os.getenv("REAL_JUMP_WAVE_END_CONFIRM_TICKS", "2"))
REAL_JUMP_HIGH_RVOL_ABSORPTION: float = float(os.getenv("REAL_JUMP_HIGH_RVOL_ABSORPTION", "8.0"))
REAL_JUMP_PRICE_RESPONSE_MIN_TICKS: int = int(os.getenv("REAL_JUMP_PRICE_RESPONSE_MIN_TICKS", "3"))
REAL_JUMP_PRIOR_RANGE_BLOCK_PCT: float = float(os.getenv("REAL_JUMP_PRIOR_RANGE_BLOCK_PCT", "8.0"))
REAL_JUMP_NEAR_PEAK_TOLERANCE_PCT: float = float(os.getenv("REAL_JUMP_NEAR_PEAK_TOLERANCE_PCT", "10.0"))
REAL_JUMP_ABSOLUTE_MAX_SPREAD_PCT: float = float(os.getenv("REAL_JUMP_ABSOLUTE_MAX_SPREAD_PCT", "10.0"))
REAL_JUMP_CONFLUENCE_SPREAD_CAP_PCT: float = float(os.getenv("REAL_JUMP_CONFLUENCE_SPREAD_CAP_PCT", "8.0"))
REAL_JUMP_POST_PEAK_MIN_BELOW_PCT: float = float(os.getenv("REAL_JUMP_POST_PEAK_MIN_BELOW_PCT", "6.0"))
REAL_JUMP_ABSORPTION_LOOKBACK_BARS: int = int(os.getenv("REAL_JUMP_ABSORPTION_LOOKBACK_BARS", "20"))
REAL_JUMP_ABSORPTION_RANGE_PCT: float = float(os.getenv("REAL_JUMP_ABSORPTION_RANGE_PCT", "6.0"))
STAGE_EE_MIN_LIQUIDITY: float = float(os.getenv("STAGE_EE_MIN_LIQUIDITY", "38"))
STAGE_EE_MIN_RRR: float = float(os.getenv("STAGE_EE_MIN_RRR", str(PREMOVE_MIN_RRR)))
STAGE_EE_PROGRESSION_TREND_MIN: float = float(os.getenv("STAGE_EE_PROGRESSION_TREND_MIN", "-1"))
STAGE_EE_MIN_CONFLUENCE: int = int(os.getenv("STAGE_EE_MIN_CONFLUENCE", "5"))
STAGE_EE_CORE_CONFLUENCE_MIN: int = int(os.getenv("STAGE_EE_CORE_CONFLUENCE_MIN", "3"))
STAGE_EE_REQUIRE_TRIGGER_AND_RESISTANCE: bool = os.getenv("STAGE_EE_REQUIRE_TRIGGER_AND_RESISTANCE", "false").lower() == "true"
STAGE_EE_CONFLUENCE_TOTAL: int = int(os.getenv("STAGE_EE_CONFLUENCE_TOTAL", "7"))
STAGE_EE_MIN_MOVE_FROM_BASE_PCT: float = float(os.getenv("STAGE_EE_MIN_MOVE_FROM_BASE_PCT", "3.5"))
STAGE_EE_MIN_SESSION_CHANGE_PCT: float = float(os.getenv("STAGE_EE_MIN_SESSION_CHANGE_PCT", "2.5"))

# EARLY_ENTRY Quality Gate — precision without delaying timing
STAGE_EE_MIN_CONFLUENCE_QUALITY: float = float(os.getenv("STAGE_EE_MIN_CONFLUENCE_QUALITY", "56"))
STAGE_EE_NO_NEWS_MIN_QUALITY: float = float(os.getenv("STAGE_EE_NO_NEWS_MIN_QUALITY", "58"))
STAGE_EE_MIN_PRICE_HOLDING_MANDATORY: float = float(os.getenv("STAGE_EE_MIN_PRICE_HOLDING_MANDATORY", "52"))
STAGE_EE_MIN_LIQUIDITY_MANDATORY: float = float(os.getenv("STAGE_EE_MIN_LIQUIDITY_MANDATORY", "42"))
STAGE_EE_MIN_RRR_QUALITY: float = float(os.getenv("STAGE_EE_MIN_RRR_QUALITY", "1.5"))
STAGE_EE_MAX_STOP_DISTANCE_PCT: float = float(os.getenv("STAGE_EE_MAX_STOP_DISTANCE_PCT", "8.0"))
STAGE_EE_MAX_REJECTION_SCORE: float = float(os.getenv("STAGE_EE_MAX_REJECTION_SCORE", "58"))
STAGE_EE_MAX_BREAKOUT_FAILURE_RISK: float = float(os.getenv("STAGE_EE_MAX_BREAKOUT_FAILURE_RISK", "58"))
STAGE_EE_MIN_VOLUME_EFFICIENCY: float = float(os.getenv("STAGE_EE_MIN_VOLUME_EFFICIENCY", "17"))
STAGE_EE_MIN_ENTRY_LOCATION: float = float(os.getenv("STAGE_EE_MIN_ENTRY_LOCATION", "52"))

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
