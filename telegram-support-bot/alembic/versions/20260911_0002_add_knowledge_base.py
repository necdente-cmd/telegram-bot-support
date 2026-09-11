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
    op.create_table(
        "knowledge_base",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("problem_text", sa.Text(), nullable=False),
        sa.Column("solution_text", sa.Text(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_kb_keywords", "knowledge_base", ["keywords"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_kb_keywords", table_name="knowledge_base")
    op.drop_table("knowledge_base")
