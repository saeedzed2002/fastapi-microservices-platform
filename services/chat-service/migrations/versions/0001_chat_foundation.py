"""chat foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_chat_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by_subject_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_created_by_subject_id", "conversations", ["created_by_subject_id"]
    )
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    op.create_table(
        "conversation_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "subject_id", name="uq_conversation_participants_subject"
        ),
    )
    op.create_index(
        "ix_conversation_participants_conversation_id",
        "conversation_participants",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_participants_subject_id", "conversation_participants", ["subject_id"]
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender_subject_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=4000), nullable=True),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content IS NULL OR length(btrim(content)) > 0", name="ck_messages_content_not_blank"
        ),
        sa.CheckConstraint("message_type = 'text'", name="ck_messages_supported_type"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sender_subject_id", "client_message_id", name="uq_messages_sender_client"
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sender_subject_id", "messages", ["sender_subject_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index(
        "ix_messages_conversation_cursor", "messages", ["conversation_id", "created_at", "id"]
    )
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_message_attachments_size_positive"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "media_asset_id", name="uq_message_attachments_asset"),
    )
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])
    op.create_index(
        "ix_message_attachments_media_asset_id", "message_attachments", ["media_asset_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_message_attachments_media_asset_id", table_name="message_attachments")
    op.drop_index("ix_message_attachments_message_id", table_name="message_attachments")
    op.drop_table("message_attachments")
    op.drop_index("ix_messages_conversation_cursor", table_name="messages")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_sender_subject_id", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversation_participants_subject_id", table_name="conversation_participants")
    op.drop_index(
        "ix_conversation_participants_conversation_id", table_name="conversation_participants"
    )
    op.drop_table("conversation_participants")
    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    op.drop_index("ix_conversations_created_by_subject_id", table_name="conversations")
    op.drop_table("conversations")
