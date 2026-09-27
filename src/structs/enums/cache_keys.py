from enum import StrEnum


class CacheKeys(StrEnum):
    EGX_STOCKS = "egx:stocks"
    EGX_STOCKS_BY_ISIN = "egx:stocks:by_isin"
    EGX_LIVE_STOCKS = "egx:stocks:live"
    EGX_STOCK_HISTORY = "egx:stocks:{isin}:history:{period}"
    EGX_LIVE = "egx:live:{name}"
    EGX_MARKET_DAY = "egx:market:day:{day}"
    EGX_MARKET_DAY_RETRY = "egx:market:day:{day}:retry"
    RATE_LIMIT = "ratelimit:{client}"
