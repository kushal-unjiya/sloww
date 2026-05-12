"""SLOW-001 baseline project-centric schema

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-03-31

This baseline creates the complete schema for M0-M2:
- Users and sign-in auditing
- Projects (first-class entities) with default project creation
- Documents (user-scoped, project-associated)
- Document metadata: summaries, chunks with section paths
- Ingestion jobs (document processing pipeline)
- Conversations and messages (project-scoped)
- Retrieval runs and citations
- Processing artifacts (intermediate results)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure schemas exist
    op.execute("CREATE SCHEMA IF NOT EXISTS public")
    op.execute("CREATE SCHEMA IF NOT EXISTS sloww_ai")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")

    # ========================================
    # USERS AND AUTH
    # ========================================
    op.create_table(
        "users",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("clerk_user_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("row_id", name="users_row_id_key"),
        sa.UniqueConstraint("clerk_user_id", name="users_clerk_user_id_key"),
        sa.UniqueConstraint("email", name="users_email_key"),
        schema="sloww_ai",
    )

    op.create_table(
        "user_sign_in_events",
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
            sa.ForeignKey("sloww_ai.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signed_in_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("clerk_session_id", sa.Text(), nullable=True),
        sa.Column(
            "auth_method", sa.Text(), server_default=sa.text("'email_otp'"), nullable=False
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="user_sign_in_events_pkey"),
        sa.UniqueConstraint("row_id", name="user_sign_in_events_row_id_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "user_sign_in_events_user_id_signed_in_at_ix",
        "user_sign_in_events",
        ["user_id", "signed_in_at"],
        schema="sloww_ai",
    )

    # ========================================
    # PROJECTS (NEW: first-class entities)
    # ========================================
    op.create_table(
        "projects",
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
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="projects_pkey"),
        sa.UniqueConstraint("row_id", name="projects_row_id_key"),
        sa.UniqueConstraint("user_id", "is_default", name="projects_user_id_is_default_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "projects_user_id_created_at_ix",
        "projects",
        ["user_id", "created_at"],
        schema="sloww_ai",
    )

    # ========================================
    # DOCUMENTS
    # ========================================
    op.create_table(
        "documents",
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
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), server_default=sa.text("'upload'"), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("1002"), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="documents_pkey"),
        sa.UniqueConstraint("row_id", name="documents_row_id_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "documents_user_id_created_at_ix",
        "documents",
        ["user_id", "created_at"],
        schema="sloww_ai",
    )

    # ========================================
    # PROJECT-DOCUMENT ASSOCIATION (NEW)
    # ========================================
    op.create_table(
        "project_documents",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.projects.id"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.documents.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="project_documents_pkey"),
        sa.UniqueConstraint("row_id", name="project_documents_row_id_key"),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            name="project_documents_project_id_document_id_key",
        ),
        schema="sloww_ai",
    )

    op.create_index(
        "project_documents_project_id_ix",
        "project_documents",
        ["project_id"],
        schema="sloww_ai",
    )

    # ========================================
    # DOCUMENT SUMMARIES (NEW)
    # ========================================
    op.create_table(
        "document_summaries",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.documents.id"),
            nullable=False,
        ),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="document_summaries_pkey"),
        sa.UniqueConstraint("row_id", name="document_summaries_row_id_key"),
        sa.UniqueConstraint("document_id", name="document_summaries_document_id_key"),
        schema="sloww_ai",
    )

    # ========================================
    # INGESTION JOBS
    # ========================================
    op.create_table(
        "ingestion_jobs",
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
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("first_failed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("max_retry_deadline_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="ingestion_jobs_pkey"),
        sa.UniqueConstraint("row_id", name="ingestion_jobs_row_id_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "ingestion_jobs_status_ix", "ingestion_jobs", ["status"], schema="sloww_ai"
    )
    op.create_index(
        "ingestion_jobs_next_retry_at_ix",
        "ingestion_jobs",
        ["next_retry_at"],
        schema="sloww_ai",
    )
    op.create_index(
        "ingestion_jobs_locked_by_ix", "ingestion_jobs", ["locked_by"], schema="sloww_ai"
    )
    op.create_index(
        "ingestion_jobs_document_id_ix",
        "ingestion_jobs",
        ["document_id"],
        schema="sloww_ai",
    )

    # ========================================
    # PROCESSING ARTIFACTS
    # ========================================
    op.create_table(
        "processing_artifacts",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.ingestion_jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.documents.id"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="processing_artifacts_pkey"),
        sa.UniqueConstraint("row_id", name="processing_artifacts_row_id_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "processing_artifacts_ingestion_job_id_ix",
        "processing_artifacts",
        ["ingestion_job_id"],
        schema="sloww_ai",
    )
    op.create_index(
        "processing_artifacts_created_at_ix",
        "processing_artifacts",
        ["created_at"],
        schema="sloww_ai",
    )
    op.create_index(
        "processing_artifacts_expires_at_ix",
        "processing_artifacts",
        ["expires_at"],
        schema="sloww_ai",
    )

    # ========================================
    # DOCUMENT CHUNKS
    # ========================================
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

    # ========================================
    # CONVERSATIONS (UPDATED: project-scoped)
    # ========================================
    op.create_table(
        "conversations",
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
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.projects.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="conversations_pkey"),
        sa.UniqueConstraint("row_id", name="conversations_row_id_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "conversations_user_id_last_message_at_ix",
        "conversations",
        ["user_id", "last_message_at"],
        schema="sloww_ai",
    )
    op.create_index(
        "conversations_project_id_ix",
        "conversations",
        ["project_id"],
        schema="sloww_ai",
    )

    # ========================================
    # MESSAGES
    # ========================================
    op.create_table(
        "messages",
        sa.Column("row_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.users.id"),
            nullable=True,
        ),
        sa.Column("role", sa.SmallInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("1200"), nullable=False),
        sa.Column("provider_used", sa.Text(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="messages_pkey"),
        sa.UniqueConstraint("row_id", name="messages_row_id_key"),
        schema="sloww_ai",
    )

    # ========================================
    # RETRIEVAL RUNS
    # ========================================
    op.create_table(
        "retrieval_runs",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sloww_ai.users.id"),
            nullable=False,
        ),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("provider_used", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="retrieval_runs_pkey"),
        sa.UniqueConstraint("row_id", name="retrieval_runs_row_id_key"),
        schema="sloww_ai",
    )

    op.create_index(
        "retrieval_runs_message_id_ix",
        "retrieval_runs",
        ["message_id"],
        schema="sloww_ai",
    )

    # ========================================
    # CITATIONS
    # ========================================
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


def downgrade() -> None:
    op.drop_table("citations", schema="sloww_ai")
    op.drop_table("retrieval_runs", schema="sloww_ai")
    op.drop_table("messages", schema="sloww_ai")
    op.drop_table("conversations", schema="sloww_ai")
    op.drop_table("document_chunks", schema="sloww_ai")
    op.drop_table("processing_artifacts", schema="sloww_ai")
    op.drop_table("ingestion_jobs", schema="sloww_ai")
    op.drop_table("document_summaries", schema="sloww_ai")
    op.drop_table("project_documents", schema="sloww_ai")
    op.drop_table("documents", schema="sloww_ai")
    op.drop_table("projects", schema="sloww_ai")
    op.drop_table("user_sign_in_events", schema="sloww_ai")
    op.drop_table("users", schema="sloww_ai")
