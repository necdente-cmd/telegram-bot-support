"""Add knowledge base table for RAG.

Revision ID: 20260911_0002
Revises: 20260830_0001
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_0002"
down_revision: Union[str, None] = "20260830_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Используем IF NOT EXISTS, чтобы миграция не падала,
    # если таблица уже была частично создана при предыдущем запуске.
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_text TEXT NOT NULL,
            solution_text TEXT NOT NULL,
            keywords TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_keywords ON knowledge_base(keywords)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_kb_keywords")
    op.execute("DROP TABLE IF EXISTS knowledge_base")
