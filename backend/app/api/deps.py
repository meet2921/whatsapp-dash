"""FastAPI dependency re-exports — one import location for all common deps."""
from app.core.database import get_db
from app.core.dependencies import (
    CurrentUser,
    OrgAdmin,
    SuperAdmin,
    get_current_user,
    get_org_admin,
    get_super_admin,
)

__all__ = [
    "get_db",
    "get_current_user",
    "get_org_admin",
    "get_super_admin",
    "CurrentUser",
    "OrgAdmin",
    "SuperAdmin",
]
