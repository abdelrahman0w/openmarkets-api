from collections.abc import AsyncGenerator
from datetime import UTC
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.services import EGXConnection
from src.services import EGXService
from src.settings import settings
from src.utils import resolve_client_ip


def get_egx_service() -> EGXService:
    return EGXConnection.get()


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with DatabaseSessions.get()() as session:
        yield session


def get_redis() -> Redis:
    return RedisConnection.get()


def get_now() -> datetime:
    return datetime.now(UTC)


def get_client_ip(request: Request) -> str | None:
    return resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get(settings.rate_limit.client_ip_header),
    )


EGXServiceDep = Annotated[EGXService, Depends(get_egx_service)]
DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
NowDep = Annotated[datetime, Depends(get_now)]
