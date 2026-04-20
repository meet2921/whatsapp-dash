"""Import all models here so Alembic's autogenerate picks them up."""
from app.models.base import Base  # noqa: F401

# Import all model modules so SQLAlchemy registers their metadata
from app.models.org import Organization, Plan  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.whatsapp import MessageTemplate, PhoneNumber, WabaAccount  # noqa: F401
from app.models.contact import Contact, ContactTag, Segment, Tag  # noqa: F401
from app.models.message import Conversation, Message  # noqa: F401
from app.models.campaign import Campaign, CampaignRecipient  # noqa: F401
from app.models.wallet import CreditRate, Invoice, Wallet, WalletTransaction  # noqa: F401
from app.models.automation import Flow, FlowExecution, FlowStep  # noqa: F401
from app.models.webhook import WebhookEvent  # noqa: F401
from app.models.media import MediaAsset  # noqa: F401
from app.models.analytics import AuditLog, DailyStat, MessageEvent  # noqa: F401
