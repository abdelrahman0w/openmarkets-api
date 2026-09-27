from collections.abc import Sequence

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.providers import logger
from src.settings import settings
from src.structs.enums import CacheKeys
from src.structs.models.responses import EGXStock
from src.utils import adapter


async def cache_stocks(redis: Redis, stocks: Sequence[EGXStock]) -> str:
    listing = adapter(list[EGXStock]).dump_json(list(stocks)).decode()
    ttl = settings.redis.cache_ttl_seconds

    try:
        async with redis.pipeline(transaction=True) as pipeline:
            pipeline.set(CacheKeys.EGX_STOCKS, listing, ex=ttl)
            pipeline.delete(CacheKeys.EGX_STOCKS_BY_ISIN)

            if stocks:
                pipeline.hset(
                    CacheKeys.EGX_STOCKS_BY_ISIN,
                    mapping={stock.isin: stock.model_dump_json() for stock in stocks},
                )
                pipeline.expire(CacheKeys.EGX_STOCKS_BY_ISIN, ttl)

            await pipeline.execute()
    except RedisError:
        logger.warning(
            "[Cache] Could Not Cache The Stocks - Redis Is Unavailable",
        )

    return listing


async def get_cached_stocks(redis: Redis) -> str | None:
    try:
        return await redis.get(CacheKeys.EGX_STOCKS)
    except RedisError:
        return None


async def get_cached_stock(redis: Redis, isin: str) -> tuple[bool, str | None]:
    try:
        async with redis.pipeline(transaction=False) as pipeline:
            pipeline.exists(CacheKeys.EGX_STOCKS_BY_ISIN)
            pipeline.hget(CacheKeys.EGX_STOCKS_BY_ISIN, isin)
            cached, stock = await pipeline.execute()
    except RedisError:
        return False, None

    return bool(cached), stock
