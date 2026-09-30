from enum import StrEnum


class CacheKeys(StrEnum):
    EGX_STOCKS = "egx:stocks"
    EGX_STOCKS_BY_ISIN = "egx:stocks:by_isin"
    EGX_LIVE_STOCKS = "egx:stocks:live"
    EGX_STOCK_HISTORY = "egx:stocks:{isin}:history:{period}"
    EGX_STOCKS_PERFORMANCE = "egx:stocks:performance:{period}"
    EGX_INDEX_LEVELS = "egx:indices:levels"
    EGX_INDEX_HISTORY = "egx:indices:{index}:history:{period}"
    EGX_INDICES_PERFORMANCE = "egx:indices:performance:{period}"
    EGX_LIVE = "egx:live:{name}"
    EGX_MARKET_DAY = "egx:market:day:{day}"
    EGX_MARKET_DAY_RETRY = "egx:market:day:{day}:retry"
    RATE_LIMIT = "ratelimit:{client}"
    GEMINI_PAUSED = "gemini:paused"
    GEMINI_BUSY_STREAK = "gemini:busy-streak"
    GEMINI_RUNNING = "gemini:running"
    GEMINI_REQUESTS = "gemini:requests:{day}"
