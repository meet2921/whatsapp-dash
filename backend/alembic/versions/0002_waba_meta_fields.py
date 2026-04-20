"""Add Meta WABA and phone number extended fields.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── waba_accounts — new Meta fields ───────────────────────────────────────
    op.add_column("waba_accounts", sa.Column("business_id", sa.String(100), nullable=True))
    op.add_column("waba_accounts", sa.Column("currency", sa.String(10), nullable=True))
    op.add_column("waba_accounts", sa.Column("timezone_id", sa.String(100), nullable=True))
    op.add_column("waba_accounts", sa.Column("message_template_namespace", sa.String(255), nullable=True))
    op.add_column("waba_accounts", sa.Column("account_review_status", sa.String(50), nullable=True))

    # ── phone_numbers — new Meta fields ───────────────────────────────────────
    op.add_column("phone_numbers", sa.Column("code_verification_status", sa.String(50), nullable=True))
    op.add_column("phone_numbers", sa.Column("platform_type", sa.String(50), nullable=True))
    op.add_column("phone_numbers", sa.Column("throughput_level", sa.String(50), nullable=True))
    op.add_column("phone_numbers", sa.Column("account_mode", sa.String(50), nullable=True))
    op.add_column("phone_numbers", sa.Column("name_status", sa.String(50), nullable=True))
    op.add_column("phone_numbers", sa.Column("last_onboarded_time", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("phone_numbers", "last_onboarded_time")
    op.drop_column("phone_numbers", "name_status")
    op.drop_column("phone_numbers", "account_mode")
    op.drop_column("phone_numbers", "throughput_level")
    op.drop_column("phone_numbers", "platform_type")
    op.drop_column("phone_numbers", "code_verification_status")

    op.drop_column("waba_accounts", "account_review_status")
    op.drop_column("waba_accounts", "message_template_namespace")
    op.drop_column("waba_accounts", "timezone_id")
    op.drop_column("waba_accounts", "currency")
    op.drop_column("waba_accounts", "business_id")
