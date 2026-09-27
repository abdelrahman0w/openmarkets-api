from collections.abc import Awaitable
from collections.abc import Callable

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.providers import logger
from src.settings import settings
from src.structs.enums import CacheKeys
from src.utils import adapter
from src.utils import params_key
from src.utils import single_flight


async def cached_json[T](
    redis: Redis,
    key: str,
    produce: Callable[[], Awaitable[T]],
    shape: type[T],
    *,
    ttl_seconds: int,
) -> str:
    try:
        if (cached := await redis.get(key)) is not None:
            return cached
    except RedisError:
        logger.warning(
            "[Cache] Skipped - Redis Is Unavailable",
            key=key,
        )

    async def produce_and_cache() -> str:
        body = adapter(shape).dump_json(await produce()).decode()

        try:
            await redis.set(key, body, ex=ttl_seconds)
        except RedisError:
            logger.warning(
                "[Cache] Could Not Cache - Redis Is Unavailable",
                key=key,
            )

        return body

    return await single_flight(key, produce_and_cache)


async def cached_live_json[T](
    redis: Redis,
    name: str,
    produce: Callable[[], Awaitable[T]],
    shape: type[T],
    params: BaseModel | None = None,
    *,
    ttl_seconds: int | None = None,
) -> str:
    return await cached_json(
        redis,
        params_key(CacheKeys.EGX_LIVE.format(name=name), params),
        produce,
        shape,
        ttl_seconds=ttl_seconds or settings.redis.live_cache_seconds,
    )
