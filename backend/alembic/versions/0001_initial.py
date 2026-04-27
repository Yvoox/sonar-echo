"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_global_admin", sa.Boolean, default=False, nullable=False),
        sa.Column("erased", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "email", name="uq_user_org_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    kb_role_enum = postgresql.ENUM("admin", "editor", "reader", "proposer",
                                    name="kb_role_enum", create_type=True)
    kb_role_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "kb_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("admin", "editor", "reader", "proposer",
                                   name="kb_role_enum", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "kb_id", name="uq_kb_membership"),
    )
    op.create_index("ix_kb_memberships_user_id", "kb_memberships", ["user_id"])
    op.create_index("ix_kb_memberships_kb_id", "kb_memberships", ["kb_id"])

    doc_state_enum = postgresql.ENUM(
        "proposed", "approved", "rejected", "ingesting", "ingested",
        "ingestion_failed", "superseded", "deleted",
        name="doc_state_enum", create_type=True,
    )
    doc_state_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_date", sa.Date, nullable=True),
        sa.Column("storage_uri", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("state", sa.Enum(*["proposed", "approved", "rejected", "ingesting", "ingested",
                                       "ingestion_failed", "superseded", "deleted"],
                                    name="doc_state_enum", create_type=False), nullable=False),
        sa.Column("version", sa.Integer, default=1, nullable=False),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_kb_id", "documents", ["kb_id"])
    op.create_index("ix_documents_state", "documents", ["state"])

    op.create_table(
        "document_state_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state", sa.Enum(*["proposed", "approved", "rejected", "ingesting", "ingested",
                                           "ingestion_failed", "superseded", "deleted"],
                                         name="doc_state_enum", create_type=False), nullable=True),
        sa.Column("to_state", sa.Enum(*["proposed", "approved", "rejected", "ingesting", "ingested",
                                         "ingestion_failed", "superseded", "deleted"],
                                       name="doc_state_enum", create_type=False), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dst_document_id", "document_state_transitions", ["document_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_usage_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("token_usage_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("saga_step", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])

    op.create_table(
        "entity_resolution_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("suggested_canonical_id", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_erc_kb_id", "entity_resolution_candidates", ["kb_id"])
    op.create_index("ix_erc_entity_id", "entity_resolution_candidates", ["entity_id"])

    gem_visibility = postgresql.ENUM("private", "kb", "org", name="gem_visibility_enum", create_type=True)
    gem_visibility.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "gems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("visibility", sa.Enum("private", "kb", "org", name="gem_visibility_enum",
                                         create_type=False), nullable=False, server_default="private"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gems_owner_id", "gems", ["owner_id"])
    op.create_index("ix_gems_kb_id", "gems", ["kb_id"])

    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gem_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("gems.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False, server_default="Nouvelle conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_conv_user_id", "chat_conversations", ["user_id"])
    op.create_index("ix_chat_conv_kb_id", "chat_conversations", ["kb_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("retrieval", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_msg_conv", "chat_messages", ["conversation_id"])

    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_message_id", "feedback", ["message_id"])

    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gem_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("gems.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("user_prompt", sa.String, nullable=False),
        sa.Column("cron_expr", sa.String(100), nullable=False),
        sa.Column("channel_type", sa.String(30), nullable=False),
        sa.Column("channel_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_automations_owner", "automations", ["owner_id"])
    op.create_index("ix_automations_kb", "automations", ["kb_id"])

    op.create_table(
        "communities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("summary_embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("member_entity_ids", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("leiden_run_id", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("ALTER TABLE communities ALTER COLUMN summary_embedding TYPE vector(1536) USING NULL")
    op.create_index("ix_communities_kb", "communities", ["kb_id"])
    op.create_index("ix_communities_run", "communities", ["leiden_run_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_actor", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_action", "audit_logs", ["action"])
    op.create_index("ix_audit_resource", "audit_logs", ["resource_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("communities")
    op.drop_table("automations")
    op.drop_table("feedback")
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
    op.drop_table("gems")
    op.drop_table("entity_resolution_candidates")
    op.drop_table("ingestion_jobs")
    op.drop_table("document_state_transitions")
    op.drop_table("documents")
    op.drop_table("kb_memberships")
    op.drop_table("knowledge_bases")
    op.drop_table("users")
    op.drop_table("organizations")
    postgresql.ENUM(name="gem_visibility_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="doc_state_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="kb_role_enum").drop(op.get_bind(), checkfirst=True)
