"""Add num_sources column to projects table

Revision ID: 0002_num_sources
Revises: 0001_baseline
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_num_sources"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "num_sources",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema="sloww_ai",
    )

    # Backfill existing rows from project_documents count
    op.execute(
        """
        UPDATE sloww_ai.projects p
        SET num_sources = (
            SELECT COUNT(*)
            FROM sloww_ai.project_documents pd
            INNER JOIN sloww_ai.documents d ON d.id = pd.document_id
            WHERE pd.project_id = p.id
              AND d.is_deleted = false
        )
        """
    )


def downgrade() -> None:
    op.drop_column("projects", "num_sources", schema="sloww_ai")
