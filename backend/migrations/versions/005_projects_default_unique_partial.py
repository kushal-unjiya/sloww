"""Fix projects default uniqueness.

The original schema used a unique constraint on (user_id, is_default), which
incorrectly limits a user to only one non-default project (is_default=false).

We instead enforce: at most one *active* default project per user.
"""

from alembic import op  # type: ignore


# revision identifiers, used by Alembic.
revision = "0005_proj_default_unique"
down_revision = "0004_qdrant_citations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTE: This migration may be re-run if an earlier attempt failed while
    # updating alembic_version (e.g. revision id > VARCHAR(32)).
    op.execute(
        """
        ALTER TABLE sloww_ai.projects
        DROP CONSTRAINT IF EXISTS projects_user_id_is_default_key
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS projects_one_default_per_user_active_ix
          ON sloww_ai.projects (user_id)
          WHERE is_default = true AND is_deleted = false
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sloww_ai.projects_one_default_per_user_active_ix")
    op.execute(
        """
        ALTER TABLE sloww_ai.projects
        ADD CONSTRAINT projects_user_id_is_default_key UNIQUE (user_id, is_default)
        """
    )

