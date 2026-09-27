from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import true
from sqlalchemy import tuple_
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import selectinload

from src.structs import tables
from src.structs.models.responses import EGXStock
from src.structs.models.responses import EGXStockQuote


STOCK_COLUMNS = (
    "reuters",
    "name",
    "name_ar",
    "market_code",
    "sector_id",
    "currency_id",
    "funds_code",
    "is_intraday",
    "has_history",
)


def _upsert(
    table: type[tables.Base],
    rows: list[dict],
    key: str,
    columns: Sequence[str],
) -> Insert:
    statement = insert(table).values(rows)

    return statement.on_conflict_do_update(
        index_elements=[key],
        set_={column: statement.excluded[column] for column in columns}
        | {"updated_at": func.now()},
        where=or_(
            *(
                getattr(table, column).is_distinct_from(statement.excluded[column])
                for column in columns
            ),
        ),
    )


async def _ids(
    session: AsyncSession,
    table: type[tables.Base],
    key: str,
    values: Sequence[object],
) -> dict:
    column = getattr(table, key)
    rows = await session.execute(select(column, table.id).where(column.in_(values)))

    return dict(rows.tuples().all())


async def _sync_indices(
    session: AsyncSession,
    memberships: dict[int, list[str]],
) -> None:
    codes = sorted(
        {code for stock_codes in memberships.values() for code in stock_codes}
    )
    if codes:
        await session.execute(
            insert(tables.EGXIndex)
            .values([{"code": code} for code in codes])
            .on_conflict_do_nothing(index_elements=["code"]),
        )

    index_ids = await _ids(session, tables.EGXIndex, "code", codes)
    pairs = [
        (stock_id, index_ids[code])
        for stock_id, stock_codes in memberships.items()
        for code in stock_codes
    ]

    removed = delete(tables.EGXStockIndex).where(
        tables.EGXStockIndex.stock_id.in_(memberships),
    )
    if pairs:
        removed = removed.where(
            tuple_(tables.EGXStockIndex.stock_id, tables.EGXStockIndex.index_id).not_in(
                pairs,
            ),
        )
    await session.execute(removed)

    if pairs:
        await session.execute(
            insert(tables.EGXStockIndex)
            .values([{"stock_id": s, "index_id": i} for s, i in pairs])
            .on_conflict_do_nothing(),
        )


async def _get_stocks(
    session: AsyncSession,
    isin: str | None = None,
) -> list[EGXStock]:
    latest = (
        select(tables.EGXStockQuote)
        .where(tables.EGXStockQuote.stock_id == tables.EGXStock.id)
        .order_by(tables.EGXStockQuote.quoted_at.desc())
        .limit(1)
        .lateral()
    )
    quote = aliased(tables.EGXStockQuote, latest)

    query = (
        select(tables.EGXStock, quote)
        .outerjoin(latest, true())
        .options(
            joinedload(tables.EGXStock.sector),
            joinedload(tables.EGXStock.currency),
            selectinload(tables.EGXStock.indices),
        )
        .order_by(tables.EGXStock.reuters)
    )
    if isin is not None:
        query = query.where(tables.EGXStock.isin == isin)

    return [
        EGXStock.model_validate(stock, from_attributes=True).model_copy(
            update={
                "quote": EGXStockQuote.model_validate(quote, from_attributes=True)
                if quote
                else None,
            },
        )
        for stock, quote in (await session.execute(query)).unique().tuples()
    ]


async def upsert_stocks(
    session: AsyncSession,
    stocks: Sequence[EGXStock],
) -> dict[str, int]:
    if not stocks:
        return {}

    sectors = {stock.sector.egx_id: stock.sector for stock in stocks if stock.sector}
    currencies = {
        stock.currency.code: stock.currency for stock in stocks if stock.currency
    }

    if sectors:
        await session.execute(
            _upsert(
                tables.EGXSector,
                [sector.model_dump() for sector in sectors.values()],
                "egx_id",
                ("name", "name_ar"),
            ),
        )
    if currencies:
        await session.execute(
            _upsert(
                tables.EGXCurrency,
                [currency.model_dump() for currency in currencies.values()],
                "code",
                ("code_ar", "name", "name_ar"),
            ),
        )

    sector_ids = await _ids(session, tables.EGXSector, "egx_id", list(sectors))
    currency_ids = await _ids(session, tables.EGXCurrency, "code", list(currencies))

    await session.execute(
        _upsert(
            tables.EGXStock,
            [
                stock.model_dump(include={"isin", *STOCK_COLUMNS})
                | {
                    "sector_id": sector_ids.get(stock.sector.egx_id)
                    if stock.sector
                    else None,
                    "currency_id": currency_ids.get(stock.currency.code)
                    if stock.currency
                    else None,
                }
                for stock in stocks
            ],
            "isin",
            STOCK_COLUMNS,
        ),
    )

    stock_ids = await _ids(
        session,
        tables.EGXStock,
        "isin",
        [stock.isin for stock in stocks],
    )
    await _sync_indices(
        session,
        {stock_ids[stock.isin]: stock.indices for stock in stocks},
    )

    return stock_ids


async def get_stocks(session: AsyncSession) -> list[EGXStock]:
    return await _get_stocks(session)


async def get_stock(session: AsyncSession, isin: str) -> EGXStock | None:
    stocks = await _get_stocks(session, isin=isin)

    return stocks[0] if stocks else None


async def get_stock_ids(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(tables.EGXStock.isin, tables.EGXStock.id))

    return dict(rows.tuples().all())


async def get_stock_id(session: AsyncSession, isin: str) -> int | None:
    return await session.scalar(
        select(tables.EGXStock.id).where(tables.EGXStock.isin == isin),
    )
