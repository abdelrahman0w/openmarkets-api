import math
from collections.abc import Collection
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.structs import tables
from src.structs.models import Page
from src.structs.models.responses import EGXNewsItem
from src.structs.models.responses import EGXNewsSummary


CHUNK_SIZE = 500

COLUMNS = (
    "date_stamp",
    "heading",
    "heading_ar",
    "content",
    "content_ar",
    "section",
    "section_ar",
    "sec_id",
    "sector_id",
    "material",
    "egx",
    "isin",
    "company_name",
    "company_name_ar",
    "attachments",
)


def _to_item(row: tables.EGXNews) -> EGXNewsItem:
    return EGXNewsItem(
        code=row.code,
        **{column: getattr(row, column) for column in COLUMNS},
    )


def _has_pdf(news: type[tables.EGXNews]) -> object:
    return news.has_pdf.is_(True)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def upsert_news(
    session: AsyncSession,
    items: Sequence[EGXNewsItem],
) -> int:
    rows = [
        {"code": item.code, **item.model_dump(include=set(COLUMNS))}
        for item in items
        if item.code is not None
    ]

    news = tables.EGXNews

    changed = 0
    for start in range(0, len(rows), CHUNK_SIZE):
        statement = insert(news).values(rows[start : start + CHUNK_SIZE])
        statement = statement.on_conflict_do_update(
            index_elements=["code"],
            set_={
                **{column: statement.excluded[column] for column in COLUMNS},
                "updated_at": func.now(),
            },
            where=or_(
                *(
                    getattr(news, column).is_distinct_from(statement.excluded[column])
                    for column in COLUMNS
                ),
            ),
        ).returning(news.id)
        changed += len((await session.execute(statement)).all())

    return changed


async def get_known_news_codes(
    session: AsyncSession,
    codes: Collection[int],
) -> set[int]:
    if not codes:
        return set()

    rows = await session.scalars(
        select(tables.EGXNews.code).where(tables.EGXNews.code.in_(codes)),
    )

    return set(rows)


async def has_news(session: AsyncSession) -> bool:
    return (await session.scalar(select(tables.EGXNews.id).limit(1))) is not None


async def get_news_item(session: AsyncSession, code: int) -> EGXNewsItem | None:
    row = await session.scalar(
        select(tables.EGXNews).where(tables.EGXNews.code == code),
    )

    return _to_item(row) if row is not None else None


async def search_news(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    timezone: str,
    sec_ids: Collection[int] | None = None,
    search_text: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    isin: str | None = None,
    has_attachments: bool = False,
) -> Page[EGXNewsItem]:
    news = tables.EGXNews
    filters = []

    if sec_ids:
        filters.append(news.sec_id.in_(sec_ids))
    if isin:
        filters.append(news.isin == isin)
    if search_text:
        pattern = f"%{_escape_like(search_text)}%"
        filters.append(news.search_text.ilike(pattern, escape="\\"))
    if has_attachments:
        filters.append(_has_pdf(news))

    local_day = func.date(func.timezone(timezone, news.date_stamp))
    if date_from:
        filters.append(local_day >= date_from)
    if date_to:
        filters.append(local_day <= date_to)

    total = await session.scalar(select(func.count()).select_from(news).where(*filters))
    rows = await session.scalars(
        select(news)
        .where(*filters)
        .order_by(news.date_stamp.desc().nulls_last(), news.code.desc())
        .offset((page - 1) * page_size)
        .limit(page_size),
    )

    return Page[EGXNewsItem](
        items=[_to_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total_count=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


async def get_news_to_summarize(
    session: AsyncSession,
    *,
    max_attempts: int,
    limit: int,
) -> list[tables.EGXNews]:
    news = tables.EGXNews
    summary = tables.EGXNewsSummary

    rows = await session.scalars(
        select(news)
        .outerjoin(summary, summary.news_code == news.code)
        .where(
            _has_pdf(news),
            or_(
                summary.id.is_(None),
                (summary.summary.is_(None)) & (summary.attempts < max_attempts),
            ),
        )
        .order_by(
            func.coalesce(summary.attempts, 0),
            news.date_stamp.desc().nulls_last(),
            news.code.desc(),
        )
        .limit(limit),
    )

    return list(rows)


async def save_news_summary(
    session: AsyncSession,
    code: int,
    *,
    summary: str,
    summary_ar: str,
    key_points: list[str],
    key_points_ar: list[str],
    model: str,
    read_attachments: bool,
) -> None:
    table = tables.EGXNewsSummary
    values = {
        "summary": summary,
        "summary_ar": summary_ar,
        "key_points": key_points,
        "key_points_ar": key_points_ar,
        "model": model,
        "read_attachments": read_attachments,
        "error": None,
    }
    statement = insert(table).values(news_code=code, attempts=1, **values)

    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["news_code"],
            set_={
                **values,
                "attempts": table.attempts + 1,
                "updated_at": func.now(),
            },
        ),
    )


async def record_summary_failure(session: AsyncSession, code: int, error: str) -> None:
    table = tables.EGXNewsSummary
    statement = insert(table).values(news_code=code, attempts=1, error=error)

    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["news_code"],
            set_={
                "attempts": table.attempts + 1,
                "error": error,
                "updated_at": func.now(),
            },
        ),
    )


async def get_news_summary(session: AsyncSession, code: int) -> EGXNewsSummary | None:
    row = await session.scalar(
        select(tables.EGXNewsSummary).where(
            tables.EGXNewsSummary.news_code == code,
            tables.EGXNewsSummary.summary.is_not(None),
        ),
    )
    if row is None or row.summary is None:
        return None

    return EGXNewsSummary(
        summary=row.summary,
        summary_ar=row.summary_ar,
        key_points=row.key_points,
        key_points_ar=row.key_points_ar,
        model=row.model,
        read_attachments=row.read_attachments,
        created_at=row.updated_at,
    )
