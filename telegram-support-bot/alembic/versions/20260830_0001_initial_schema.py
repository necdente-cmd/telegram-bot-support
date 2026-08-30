"""Initial schema: keywords, responsible users, banned users.

Revision ID: 20260830_0001
Revises:
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("word", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word"),
    )

    op.create_table(
        "responsible_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "banned_users",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("banned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("banned_users")
    op.drop_table("responsible_users")
    op.drop_table("keywords")
