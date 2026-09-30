from collections.abc import AsyncGenerator
from datetime import UTC
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions import auth as auth_actions
from src.exceptions import ForbiddenError
from src.exceptions import UnauthorizedError
from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.services import EGXConnection
from src.services import EGXService
from src.services import ResendConnection
from src.services import ResendService
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


def get_resend() -> ResendService | None:
    return ResendConnection.get()


EGXServiceDep = Annotated[EGXService, Depends(get_egx_service)]
DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
NowDep = Annotated[datetime, Depends(get_now)]
ResendDep = Annotated[ResendService | None, Depends(get_resend)]
ClientIPDep = Annotated[str | None, Depends(get_client_ip)]


async def get_user_id(
    request: Request,
    session: DBSessionDep,
    redis: RedisDep,
    now: NowDep,
) -> UUID | None:
    token = request.cookies.get(settings.auth.cookie_name)
    if not token:
        return None

    return await auth_actions.resolve_session(
        session,
        redis,
        token,
        now=now,
    )


async def require_user_id(
    user_id: Annotated[UUID | None, Depends(get_user_id)],
) -> UUID:
    if user_id is None:
        raise UnauthorizedError("Sign in to continue")

    return user_id


async def require_session(
    request: Request,
    session: DBSessionDep,
    redis: RedisDep,
    now: NowDep,
) -> None:
    if not settings.auth.required:
        return

    if await get_user_id(request, session, redis, now) is None:
        raise UnauthorizedError("Sign in to continue")


def require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors.origins:
        raise ForbiddenError("This origin may not do that")


UserIDDep = Annotated[UUID, Depends(require_user_id)]
