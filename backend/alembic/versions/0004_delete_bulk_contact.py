"""Add cascade delete for contact → conversations → messages.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── conversations.contact_id → contacts.id (ADD CASCADE) ───────────────
    op.drop_constraint(
        "conversations_contact_id_fkey",
        "conversations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "conversations_contact_id_fkey",
        "conversations",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── messages.conversation_id → conversations.id (ADD CASCADE) ──────────
    op.drop_constraint(
        "messages_conversation_id_fkey",
        "messages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # revert messages FK
    op.drop_constraint(
        "messages_conversation_id_fkey",
        "messages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
    )

    # revert conversations FK
    op.drop_constraint(
        "conversations_contact_id_fkey",
        "conversations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "conversations_contact_id_fkey",
        "conversations",
        "contacts",
        ["contact_id"],
        ["id"],
    )