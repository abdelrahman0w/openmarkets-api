import asyncio
import json
from collections.abc import AsyncGenerator
from collections.abc import Callable
from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport
from httpx import AsyncClient
from sqlalchemy import URL
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.dependencies import get_db_session
from src.dependencies import get_egx_service
from src.dependencies import get_now
from src.dependencies import get_redis
from src.main import app
from src.providers import setup_logging
from src.services import EGXService
from src.settings import settings
from src.structs.enums import EGXMarketStatusValue
from src.structs.models.responses import EGXMarketStatus
from src.structs.tables import Base


OPEN_NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
CLOSED_NOW = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


@pytest.fixture
def egx() -> AsyncMock:
    service = AsyncMock(spec=EGXService)
    service.market_status.return_value = EGXMarketStatus(
        status=EGXMarketStatusValue.OPEN,
    )

    return service


@pytest.fixture
async def redis() -> AsyncGenerator[FakeAsyncRedis]:
    client = FakeAsyncRedis(decode_responses=True)

    yield client

    await client.aclose()


@pytest.fixture
def now() -> datetime:
    return CLOSED_NOW


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
async def client(
    egx: AsyncMock,
    redis: FakeAsyncRedis,
    session: AsyncSession,
    now: datetime,
) -> AsyncGenerator[AsyncClient]:
    app.dependency_overrides[get_egx_service] = lambda: egx
    app.dependency_overrides[get_now] = lambda: now
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_db_session] = lambda: session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


@pytest.fixture
def json_lines(
    capsys: pytest.CaptureFixture[str],
) -> Generator[Callable[[], list[dict]]]:
    setup_logging(level="DEBUG", json_logs=True)

    def read() -> list[dict]:
        return [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    yield read

    setup_logging(level="WARNING", json_logs=True)


@pytest.fixture(scope="session")
def database_url() -> URL:
    url = settings.database.url

    async def prepare() -> None:
        admin = create_async_engine(
            url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("select 1 from pg_database where datname = :name"),
                {"name": url.database},
            )
            if not exists:
                await connection.execute(text(f'create database "{url.database}"'))

        await admin.dispose()

        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        await engine.dispose()

    try:
        asyncio.run(prepare())
    except OSError as exc:
        pytest.skip(f"postgres is not available: {exc}")

    return url


@pytest.fixture
async def db_connection(
    database_url: URL,
) -> AsyncGenerator[AsyncConnection]:
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
    )

    async with engine.connect() as connection:
        transaction = await connection.begin()

        yield connection

        await transaction.rollback()

    await engine.dispose()


@pytest.fixture
def session_factory(
    db_connection: AsyncConnection,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    async with session_factory() as db_session:
        yield db_session


@pytest.fixture
def db_client(
    client: AsyncClient,
    db_session: AsyncSession,
) -> AsyncClient:
    app.dependency_overrides[get_db_session] = lambda: db_session

    return client
