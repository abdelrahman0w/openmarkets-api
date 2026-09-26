from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.settings import settings
from src.utils import resolve_client_ip


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with DatabaseSessions.get()() as session:
        yield session


def get_redis() -> Redis:
    return RedisConnection.get()


def get_client_ip(request: Request) -> str | None:
    return resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get(settings.rate_limit.client_ip_header),
    )


DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
