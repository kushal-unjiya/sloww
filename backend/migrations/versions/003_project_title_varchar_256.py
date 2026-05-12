"""Limit projects.title to 256 characters (VARCHAR)

Revision ID: 0003_title_len
Revises: 0002_num_sources
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_title_len"
down_revision = "0002_num_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE sloww_ai.projects SET title = left(title, 256) "
            "WHERE char_length(title) > 256"
        )
    )
    op.alter_column(
        "projects",
        "title",
        existing_type=sa.Text(),
        type_=sa.String(256),
        existing_nullable=False,
        schema="sloww_ai",
    )


def downgrade() -> None:
    op.alter_column(
        "projects",
        "title",
        existing_type=sa.String(256),
        type_=sa.Text(),
        existing_nullable=False,
        schema="sloww_ai",
    )
