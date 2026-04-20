"""Initial schema — all tables with Upgrades 1-7 baked in.

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── plans ──────────────────────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("monthly_fee", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("msg_limit", sa.Integer, nullable=True),
        sa.Column("contact_limit", sa.Integer, nullable=True),
        sa.Column("features", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )

    # ── organizations ──────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_suspended", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("suspension_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("super_admin", "org_admin", "agent", "viewer", name="userrole"), nullable=False, server_default="agent"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferences", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── waba_accounts ──────────────────────────────────────────────────────
    op.create_table(
        "waba_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("waba_id", sa.String(100), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("business_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("waba_id", name="uq_waba_accounts_waba_id"),
    )
    op.create_index("ix_waba_accounts_org_id", "waba_accounts", ["org_id"])

    # ── phone_numbers ──────────────────────────────────────────────────────
    op.create_table(
        "phone_numbers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("waba_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("waba_accounts.id"), nullable=False),
        sa.Column("phone_number_id", sa.String(100), nullable=False),
        sa.Column("display_number", sa.String(20), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("quality_rating", sa.String(20), nullable=True),
        sa.Column("messaging_limit", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("phone_number_id", name="uq_phone_numbers_phone_number_id"),
    )
    op.create_index("ix_phone_numbers_org_id", "phone_numbers", ["org_id"])

    # ── message_templates ──────────────────────────────────────────────────
    op.create_table(
        "message_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("waba_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("waba_accounts.id"), nullable=False),
        sa.Column("meta_template_id", sa.String(100), nullable=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("category", sa.Enum("MARKETING", "UTILITY", "AUTHENTICATION", name="templatecategory"), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("status", sa.Enum("PENDING", "APPROVED", "REJECTED", "PAUSED", name="templatestatus"), nullable=False, server_default="PENDING"),
        sa.Column("components", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "name", "language", name="uq_template_org_name_lang"),
    )
    op.create_index("ix_message_templates_org_status", "message_templates", ["org_id", "status"])

    # ── contacts ───────────────────────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("is_opted_in", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("opted_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_status", sa.String(50), nullable=True),
        sa.Column("attributes", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "phone", name="uq_contact_org_phone"),
    )
    op.create_index("ix_contacts_org_id", "contacts", ["org_id"])
    op.create_index("ix_contacts_org_opted_in", "contacts", ["org_id", "is_opted_in"])
    op.execute("CREATE INDEX ix_contacts_attributes ON contacts USING gin(attributes)")

    # ── tags ───────────────────────────────────────────────────────────────
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.UniqueConstraint("org_id", "name", name="uq_tag_org_name"),
    )
    op.create_index("ix_tags_org_id", "tags", ["org_id"])

    # ── contact_tags ───────────────────────────────────────────────────────
    op.create_table(
        "contact_tags",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── segments ───────────────────────────────────────────────────────────
    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filter_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("contact_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_segments_org_id", "segments", ["org_id"])

    # ── conversations ──────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("phone_number_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("phone_numbers.id"), nullable=False),
        sa.Column("status", sa.Enum("open", "resolved", "pending", name="conversationstatus"), nullable=False, server_default="open"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
        # Upgrade 6: Conversation locking
        sa.Column("locked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversations_org_id", "conversations", ["org_id"])
    op.create_index("ix_conversations_org_status", "conversations", ["org_id", "status"])
    op.create_index("ix_conversations_org_contact", "conversations", ["org_id", "contact_id"])

    # ── campaigns (needed before messages for FK) ──────────────────────────
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("message_templates.id"), nullable=True),
        sa.Column("phone_number_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("phone_numbers.id"), nullable=True),
        sa.Column("status", sa.Enum("draft", "scheduled", "running", "paused", "completed", "failed", name="campaignstatus"), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_recipients", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("delivered_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("read_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("actual_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_campaigns_org_id", "campaigns", ["org_id"])
    op.create_index("ix_campaigns_org_status", "campaigns", ["org_id", "status"])

    # ── messages ───────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("wa_message_id", sa.String(100), nullable=True),
        sa.Column("direction", sa.Enum("inbound", "outbound", name="messagedirection"), nullable=False),
        sa.Column("status", sa.Enum("queued", "sent", "delivered", "read", "failed", name="messagestatus"), nullable=False, server_default="queued"),
        sa.Column("message_type", sa.String(30), nullable=False, server_default="text"),
        sa.Column("content", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("message_templates.id"), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("cost_credits", sa.Numeric(10, 6), nullable=True),
        # Upgrade 1: Idempotency
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("wa_message_id", name="uq_messages_wa_message_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_messages_idempotency_key"),
    )
    op.create_index("ix_messages_org_id", "messages", ["org_id"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_index("ix_messages_org_campaign", "messages", ["org_id", "campaign_id"])

    # ── campaign_recipients ────────────────────────────────────────────────
    op.create_table(
        "campaign_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("template_variables", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.Enum("queued", "sent", "delivered", "read", "failed", name="recipientstatus"), nullable=False, server_default="queued"),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_campaign_recipients_campaign_status", "campaign_recipients", ["campaign_id", "status"])

    # ── wallets ────────────────────────────────────────────────────────────
    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("balance", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("low_balance_threshold", sa.Numeric(10, 4), nullable=False, server_default="500"),
        sa.Column("auto_recharge_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("auto_recharge_amount", sa.Numeric(10, 4), nullable=True),
        sa.Column("auto_recharge_trigger", sa.Numeric(10, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", name="uq_wallets_org_id"),
    )

    # ── credit_rates ───────────────────────────────────────────────────────
    op.create_table(
        "credit_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_type", sa.String(50), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("meta_cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("selling_price_inr", sa.Numeric(10, 4), nullable=False),
        sa.Column("usd_to_inr_rate", sa.Numeric(8, 4), nullable=False, server_default="83.5"),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_credit_rates_type_country_active", "credit_rates", ["conversation_type", "country_code", "is_active"])

    # ── wallet_transactions ────────────────────────────────────────────────
    op.create_table(
        "wallet_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=False),
        sa.Column("type", sa.Enum("credit", "debit", "refund", "adjustment", name="transactiontype"), nullable=False),
        # Upgrade 2: Two-phase billing
        sa.Column("status", sa.Enum("pending", "confirmed", "rolled_back", name="transactionstatus"), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 4), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("reference_id", sa.String(255), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=True),
        # Upgrade 1: Idempotency
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_wallet_tx_org_idem"),
    )
    op.create_index("ix_wallet_transactions_org_id", "wallet_transactions", ["org_id"])
    op.create_index("ix_wallet_transactions_org_created", "wallet_transactions", ["org_id", "created_at"])

    # ── invoices ───────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("invoice_number", sa.String(50), nullable=False),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("amount_inr", sa.Numeric(12, 4), nullable=False),
        sa.Column("gst_amount", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("razorpay_payment_id", sa.String(100), nullable=True),
        sa.Column("pdf_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
    )
    op.create_index("ix_invoices_org_id", "invoices", ["org_id"])

    # ── flows ──────────────────────────────────────────────────────────────
    op.create_table(
        "flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("use_ai", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ai_system_prompt", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_flows_org_id", "flows", ["org_id"])
    op.create_index("ix_flows_org_active", "flows", ["org_id", "is_active"])

    # ── flow_steps ─────────────────────────────────────────────────────────
    op.create_table(
        "flow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("step_type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("next_step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flow_steps.id"), nullable=True),
        sa.UniqueConstraint("flow_id", "step_order", name="uq_flow_step_order"),
    )

    # ── flow_executions ────────────────────────────────────────────────────
    op.create_table(
        "flow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("current_step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flow_steps.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_flow_executions_org_id", "flow_executions", ["org_id"])

    # ── webhook_events (Upgrade 4) ─────────────────────────────────────────
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("processed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        # Upgrade 1: Idempotency
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("source", "idempotency_key", name="uq_webhook_source_idem"),
    )
    op.create_index("ix_webhook_events_processed_retry", "webhook_events", ["processed", "retry_count"])

    # ── media_assets (Upgrade 7) ───────────────────────────────────────────
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("s3_key", sa.String(500), nullable=True),
        sa.Column("public_url", sa.String(1000), nullable=True),
        sa.Column("status", sa.Enum("pending", "processing", "completed", "failed", name="mediastatus"), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_media_assets_org_id", "media_assets", ["org_id"])
    op.create_index("ix_media_assets_org_status", "media_assets", ["org_id", "status"])

    # ── message_events ─────────────────────────────────────────────────────
    op.create_table(
        "message_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_message_events_org_id", "message_events", ["org_id"])

    # ── daily_stats ────────────────────────────────────────────────────────
    op.create_table(
        "daily_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("messages_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("messages_delivered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("messages_read", sa.Integer, nullable=False, server_default="0"),
        sa.Column("messages_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("campaigns_run", sa.Integer, nullable=False, server_default="0"),
        sa.Column("credits_consumed", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint("org_id", "date", name="uq_daily_stats_org_date"),
    )
    op.create_index("ix_daily_stats_org_id", "daily_stats", ["org_id"])

    # ── audit_log ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_audit_log_org_id", "audit_log", ["org_id"])
    op.create_index("ix_audit_log_org_created", "audit_log", ["org_id", "created_at"])


def downgrade() -> None:
    # Drop tables in reverse FK dependency order
    op.drop_table("audit_log")
    op.drop_table("daily_stats")
    op.drop_table("message_events")
    op.drop_table("media_assets")
    op.drop_table("webhook_events")
    op.drop_table("flow_executions")
    op.drop_table("flow_steps")
    op.drop_table("flows")
    op.drop_table("invoices")
    op.drop_table("wallet_transactions")
    op.drop_table("credit_rates")
    op.drop_table("wallets")
    op.drop_table("campaign_recipients")
    op.drop_table("messages")
    op.drop_table("campaigns")
    op.drop_table("conversations")
    op.drop_table("segments")
    op.drop_table("contact_tags")
    op.drop_table("tags")
    op.drop_table("contacts")
    op.drop_table("message_templates")
    op.drop_table("phone_numbers")
    op.drop_table("waba_accounts")
    op.drop_table("users")
    op.drop_table("organizations")
    op.drop_table("plans")

    # Drop enums
    for enum_name in [
        "mediastatus", "transactionstatus", "transactiontype",
        "recipientstatus", "campaignstatus", "messagestatus",
        "messagedirection", "conversationstatus", "templatestatus",
        "templatecategory", "userrole",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
