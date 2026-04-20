"""Add local_qr_codes table for storing QR codes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_qr_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("phone_internal_id", UUID(as_uuid=True), sa.ForeignKey("phone_numbers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("prefilled_message", sa.Text, nullable=False),
        sa.Column("deep_link_url", sa.Text, nullable=False),
        sa.Column("qr_image_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_qr_codes")
