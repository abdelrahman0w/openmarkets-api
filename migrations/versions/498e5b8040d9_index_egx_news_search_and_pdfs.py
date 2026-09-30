"""index egx news search and pdfs

Revision ID: 498e5b8040d9
Revises: 8a34993a09ae
Create Date: 2026-09-29 17:37:43

"""

from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

from src.structs.tables.egx.news import HAS_PDF
from src.structs.tables.egx.news import SEARCH_TEXT


# revision identifiers, used by Alembic.
revision: str = "498e5b8040d9"
down_revision: Union[str, Sequence[str], None] = "8a34993a09ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # a trusted extension, the database's owner creates it, no superuser needed
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "egx_news",
        sa.Column("search_text", sa.Text(), sa.Computed(SEARCH_TEXT), nullable=True),
    )
    op.add_column(
        "egx_news",
        sa.Column("has_pdf", sa.Boolean(), sa.Computed(HAS_PDF), nullable=True),
    )
    op.create_index(
        op.f("ix_egx_news_search_text"),
        "egx_news",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index(
        op.f("ix_egx_news_has_pdf_date_stamp"),
        "egx_news",
        ["has_pdf", "date_stamp"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_egx_news_has_pdf_date_stamp"), table_name="egx_news")
    op.drop_index(op.f("ix_egx_news_search_text"), table_name="egx_news")
    op.drop_column("egx_news", "has_pdf")
    op.drop_column("egx_news", "search_text")
