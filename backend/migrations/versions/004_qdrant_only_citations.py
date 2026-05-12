"""Drop document_chunks; citations reference Qdrant chunk_id (text) only.

Revision ID: 0004_qdrant_citations
Revises: 0003_title_len
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_qdrant_citations"
down_revision = "0003_title_len"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("citations", schema="sloww_ai")
    op.drop_table("document_chunks", schema="sloww_ai")

    op.create_table(
        "citations",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retrieval_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.retrieval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("qdrant_point_id", sa.Text(), nullable=True),
        sa.Column("citation_order", sa.Integer(), nullable=False),
        sa.Column("excerpt_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(precision=53), nullable=True),
        sa.Column("rerank_score", sa.Float(precision=53), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="citations_pkey"),
        sa.UniqueConstraint("row_id", name="citations_row_id_key"),
        sa.UniqueConstraint(
            "message_id",
            "citation_order",
            name="citations_message_id_citation_order_key",
        ),
        schema="sloww_ai",
    )
    op.create_index(
        "citations_message_id_ix",
        "citations",
        ["message_id"],
        schema="sloww_ai",
    )


def downgrade() -> None:
    op.drop_table("citations", schema="sloww_ai")

    op.create_table(
        "document_chunks",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.users.id"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.documents.id"),
            nullable=False,
        ),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_label", sa.Text(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("excerpt_text", sa.Text(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "is_superseded", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="document_chunks_pkey"),
        sa.UniqueConstraint("row_id", name="document_chunks_row_id_key"),
        sa.UniqueConstraint("qdrant_point_id", name="document_chunks_qdrant_point_id_key"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="document_chunks_document_id_chunk_index_key",
        ),
        schema="sloww_ai",
    )
    op.create_index(
        "document_chunks_document_user_active_ix",
        "document_chunks",
        ["document_id", "user_id", "is_active"],
        schema="sloww_ai",
    )

    op.create_table(
        "citations",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.messages.id"),
            nullable=False,
        ),
        sa.Column(
            "retrieval_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.retrieval_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.document_chunks.id"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.documents.id"),
            nullable=False,
        ),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("citation_order", sa.Integer(), nullable=False),
        sa.Column("excerpt_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(precision=53), nullable=True),
        sa.Column("rerank_score", sa.Float(precision=53), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="citations_pkey"),
        sa.UniqueConstraint("row_id", name="citations_row_id_key"),
        sa.UniqueConstraint(
            "message_id",
            "citation_order",
            name="citations_message_id_citation_order_key",
        ),
        schema="sloww_ai",
    )
    op.create_index(
        "citations_message_id_ix",
        "citations",
        ["message_id"],
        schema="sloww_ai",
    )
