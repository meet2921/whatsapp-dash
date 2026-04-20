"""Contacts, tags, and CSV/Excel import.

GET    /contacts              — list contacts (search, tag filter, pagination)
POST   /contacts              — create contact
GET    /contacts/{id}         — get contact
PATCH  /contacts/{id}         — update contact (name, email, attributes, opt-in)
DELETE /contacts/{id}         — delete contact
POST   /contacts/import       — bulk import from CSV or Excel (multipart)
GET    /contacts/export       — export as CSV

GET    /contacts/tags         — list all tags
POST   /contacts/tags         — create tag
DELETE /contacts/tags/{id}    — delete tag
POST   /contacts/{id}/tags    — add tag to contact
DELETE /contacts/{id}/tags/{tag_id} — remove tag from contact
"""
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import CurrentUser, OrgAdmin
from app.models.contact import Contact, ContactTag, Segment, Tag

router = APIRouter(prefix="/contacts", tags=["Contacts"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    phone: str
    name: str | None = None
    email: str | None = None
    language: str = "en"
    is_opted_in: bool = True
    attributes: dict = {}


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    language: str | None = None
    is_opted_in: bool | None = None
    lead_status: str | None = None
    attributes: dict | None = None


class TagCreate(BaseModel):
    name: str
    color: str | None = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    phone: str
    name: str | None
    email: str | None
    language: str
    is_opted_in: bool
    opted_in_at: datetime | None
    opted_out_at: datetime | None
    lead_status: str | None
    attributes: dict
    tags: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class TagResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    color: str | None

    model_config = {"from_attributes": True}


def _contact_to_dict(c: Contact) -> dict:
    return {
        "id": str(c.id),
        "org_id": str(c.org_id),
        "phone": c.phone,
        "name": c.name,
        "email": c.email,
        "language": c.language,
        "is_opted_in": c.is_opted_in,
        "opted_in_at": c.opted_in_at.isoformat() if c.opted_in_at else None,
        "opted_out_at": c.opted_out_at.isoformat() if c.opted_out_at else None,
        "lead_status": c.lead_status,
        "attributes": c.attributes or {},
        "tags": [{"id": str(t.id), "name": t.name, "color": t.color} for t in (c.tags or [])],
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ── Tag routes (MUST be before /{contact_id}) ─────────────────────────────────

@router.get("/tags")
async def list_tags(current_user: CurrentUser, db: DbDep) -> list[dict]:
    result = await db.execute(select(Tag).where(Tag.org_id == current_user.org_id).order_by(Tag.name))
    return [{"id": str(t.id), "org_id": str(t.org_id), "name": t.name, "color": t.color}
            for t in result.scalars().all()]


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(body: TagCreate, current_user: OrgAdmin, db: DbDep) -> dict:
    existing = await db.execute(select(Tag).where(Tag.org_id == current_user.org_id, Tag.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Tag '{body.name}' already exists")
    tag = Tag(org_id=current_user.org_id, name=body.name, color=body.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return {"id": str(tag.id), "org_id": str(tag.org_id), "name": tag.name, "color": tag.color}


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> None:
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.org_id == current_user.org_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()


# ── Import helpers ────────────────────────────────────────────────────────────

def _decode_csv(content: bytes) -> list[dict]:
    """Decode CSV bytes, auto-detecting encoding. Returns list of dicts."""
    import chardet
    # Try UTF-8 with BOM first, then auto-detect
    for enc in ("utf-8-sig", "utf-8"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    else:
        detected = chardet.detect(content)
        enc = detected.get("encoding") or "latin-1"
        text = content.decode(enc, errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "phone" not in [f.lower().strip() for f in reader.fieldnames]:
        raise HTTPException(status_code=400, detail="File must have a 'phone' column")
    return [{k.lower().strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def _parse_excel(content: bytes) -> list[dict]:
    """Parse Excel (.xlsx) bytes. Returns list of dicts with lowercase keys."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise HTTPException(status_code=400, detail="Excel file has no active sheet")

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel file is empty")

    # First row = headers
    headers = [str(h).lower().strip() if h is not None else "" for h in rows[0]]
    if "phone" not in headers:
        raise HTTPException(status_code=400, detail="File must have a 'phone' column")

    result = []
    for row in rows[1:]:
        d = {}
        for i, val in enumerate(row):
            if i < len(headers) and headers[i]:
                d[headers[i]] = str(val).strip() if val is not None else ""
        result.append(d)
    wb.close()
    return result


# ── Import (MUST be before /{contact_id}) ─────────────────────────────────────

@router.post("/import", status_code=status.HTTP_200_OK)
async def import_contacts(
    current_user: OrgAdmin,
    db: DbDep,
    file: UploadFile = File(...),
) -> dict:
    """Import contacts from CSV or Excel (.xlsx).
    Expected columns: phone (required), name, email, language, opted_in
    Returns: { inserted, updated, skipped, errors }
    """
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only CSV and Excel (.xlsx) files are supported")

    content = await file.read()

    try:
        if filename.endswith(".csv"):
            rows = _decode_csv(content)
        else:
            rows = _parse_excel(content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc

    inserted = updated = skipped = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc)
    seen_phones: set[str] = set()  # deduplicate within this import batch

    for i, row in enumerate(rows, start=2):  # row 1 = header
        phone = row.get("phone", "").strip()
        if not phone:
            skipped += 1
            continue
        if not phone.startswith("+"):
            phone = "+" + phone

        # Skip duplicate phones within the same file
        if phone in seen_phones:
            skipped += 1
            continue
        seen_phones.add(phone)

        try:
            async with db.begin_nested():  # SAVEPOINT — rolls back only this row on error
                # Check existing
                existing_result = await db.execute(
                    select(Contact).where(Contact.org_id == current_user.org_id, Contact.phone == phone)
                )
                existing = existing_result.scalar_one_or_none()

                opted_in_raw = row.get("opted_in", "true").lower()
                is_opted_in = opted_in_raw not in ("0", "false", "no", "n")

                if existing:
                    if row.get("name"):
                        existing.name = row["name"]  # type: ignore[assignment]
                    if row.get("email"):
                        existing.email = row["email"]  # type: ignore[assignment]
                    if row.get("language"):
                        existing.language = row["language"]  # type: ignore[assignment]
                    existing.is_opted_in = is_opted_in  # type: ignore[assignment]
                    updated += 1
                else:
                    c = Contact(
                        org_id=current_user.org_id,
                        phone=phone,
                        name=row.get("name") or None,
                        email=row.get("email") or None,
                        language=row.get("language", "en") or "en",
                        is_opted_in=is_opted_in,
                        opted_in_at=now if is_opted_in else None,
                    )
                    db.add(c)
                    await db.flush()
                    inserted += 1
        except Exception as e:
            errors.append(f"Row {i} ({phone}): {str(e)[:120]}")
            continue

    await db.commit()
    logger.info("contacts.imported", org_id=str(current_user.org_id),
                inserted=inserted, updated=updated, skipped=skipped)
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors[:20]}


# ── Bulk delete (MUST be before /{contact_id}) ────────────────────────────────

class BulkDeleteBody(BaseModel):
    ids: list[uuid.UUID] | None = None       # delete specific IDs
    all_matching: bool = False               # delete ALL matching current filters
    search: str | None = None               # must match list filters exactly
    tag_id: uuid.UUID | None = None
    opted_in: bool | None = None


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_contacts(body: BulkDeleteBody, current_user: OrgAdmin, db: DbDep) -> dict:
    """Delete multiple contacts at once.

    Two modes:
    - ids: delete by explicit list of UUIDs (current page selection)
    - all_matching=true: delete all contacts matching search/tag/opted_in filters
    """
    from sqlalchemy import delete as sql_delete

    if body.ids:
        result = await db.execute(
            sql_delete(Contact).where(
                Contact.org_id == current_user.org_id,
                Contact.id.in_(body.ids),
            )
        )
        deleted = result.rowcount
    elif body.all_matching:
        q = select(Contact.id).where(Contact.org_id == current_user.org_id)
        if body.search:
            like = f"%{body.search}%"
            q = q.where(
                (Contact.phone.ilike(like)) |
                (Contact.name.ilike(like)) |
                (Contact.email.ilike(like))
            )
        if body.opted_in is not None:
            q = q.where(Contact.is_opted_in == body.opted_in)
        if body.tag_id:
            q = q.join(ContactTag, ContactTag.contact_id == Contact.id).where(ContactTag.tag_id == body.tag_id)

        ids_result = await db.execute(q)
        ids = [r[0] for r in ids_result.all()]
        result = await db.execute(
            sql_delete(Contact).where(Contact.id.in_(ids))
        )
        deleted = result.rowcount
    else:
        return {"deleted": 0}

    await db.commit()
    logger.info("contacts.bulk_deleted", org_id=str(current_user.org_id), deleted=deleted)
    return {"deleted": deleted}


# ── Contact CRUD ──────────────────────────────────────────────────────────────

@router.get("")
async def list_contacts(
    current_user: CurrentUser,
    db: DbDep,
    search: str | None = Query(default=None),
    tag_id: uuid.UUID | None = Query(default=None),
    opted_in: bool | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
) -> dict:
    """List contacts with optional search, tag filter, and pagination."""
    q = (
        select(Contact)
        .where(Contact.org_id == current_user.org_id)
        .options(selectinload(Contact.tags))
        .order_by(Contact.created_at.desc())
    )
    if search:
        like = f"%{search}%"
        q = q.where(
            (Contact.phone.ilike(like)) |
            (Contact.name.ilike(like)) |
            (Contact.email.ilike(like))
        )
    if opted_in is not None:
        q = q.where(Contact.is_opted_in == opted_in)
    if tag_id:
        q = q.join(ContactTag, ContactTag.contact_id == Contact.id).where(ContactTag.tag_id == tag_id)

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(q.offset(offset).limit(limit))
    contacts = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_contact_to_dict(c) for c in contacts],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(body: ContactCreate, current_user: OrgAdmin, db: DbDep) -> dict:
    existing = await db.execute(
        select(Contact).where(Contact.org_id == current_user.org_id, Contact.phone == body.phone)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Contact with phone {body.phone} already exists")

    now = datetime.now(timezone.utc)
    contact = Contact(
        org_id=current_user.org_id,
        phone=body.phone,
        name=body.name,
        email=body.email,
        language=body.language,
        is_opted_in=body.is_opted_in,
        opted_in_at=now if body.is_opted_in else None,
        attributes=body.attributes,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact, ["tags"])
    logger.info("contact.created", org_id=str(current_user.org_id), phone=body.phone)
    return _contact_to_dict(contact)


@router.get("/{contact_id}")
async def get_contact(contact_id: uuid.UUID, current_user: CurrentUser, db: DbDep) -> dict:
    result = await db.execute(
        select(Contact)
        .where(Contact.id == contact_id, Contact.org_id == current_user.org_id)
        .options(selectinload(Contact.tags))
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_to_dict(c)


@router.patch("/{contact_id}")
async def update_contact(contact_id: uuid.UUID, body: ContactUpdate, current_user: OrgAdmin, db: DbDep) -> dict:
    result = await db.execute(
        select(Contact)
        .where(Contact.id == contact_id, Contact.org_id == current_user.org_id)
        .options(selectinload(Contact.tags))
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")

    now = datetime.now(timezone.utc)
    if body.name is not None:
        c.name = body.name  # type: ignore[assignment]
    if body.email is not None:
        c.email = body.email  # type: ignore[assignment]
    if body.language is not None:
        c.language = body.language  # type: ignore[assignment]
    if body.lead_status is not None:
        c.lead_status = body.lead_status  # type: ignore[assignment]
    if body.attributes is not None:
        c.attributes = body.attributes  # type: ignore[assignment]
    if body.is_opted_in is not None:
        if body.is_opted_in and not c.is_opted_in:
            c.opted_in_at = now  # type: ignore[assignment]
            c.opted_out_at = None  # type: ignore[assignment]
        elif not body.is_opted_in and c.is_opted_in:
            c.opted_out_at = now  # type: ignore[assignment]
        c.is_opted_in = body.is_opted_in  # type: ignore[assignment]

    await db.commit()
    await db.refresh(c, ["tags"])
    return _contact_to_dict(c)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> None:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.org_id == current_user.org_id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(c)
    await db.commit()


# ── Contact tag management ─────────────────────────────────────────────────────

@router.post("/{contact_id}/tags", status_code=status.HTTP_200_OK)
async def add_tag_to_contact(
    contact_id: uuid.UUID, body: dict, current_user: OrgAdmin, db: DbDep
) -> dict:
    tag_id = body.get("tag_id")
    if not tag_id:
        raise HTTPException(status_code=400, detail="tag_id is required")

    c_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.org_id == current_user.org_id)
        .options(selectinload(Contact.tags))
    )
    c = c_result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")

    t_result = await db.execute(
        select(Tag).where(Tag.id == uuid.UUID(str(tag_id)), Tag.org_id == current_user.org_id)
    )
    tag = t_result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    if tag not in c.tags:
        c.tags.append(tag)
        await db.commit()
        await db.refresh(c, ["tags"])
    return _contact_to_dict(c)


@router.delete("/{contact_id}/tags/{tag_id}", status_code=status.HTTP_200_OK)
async def remove_tag_from_contact(
    contact_id: uuid.UUID, tag_id: uuid.UUID, current_user: OrgAdmin, db: DbDep
) -> dict:
    c_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.org_id == current_user.org_id)
        .options(selectinload(Contact.tags))
    )
    c = c_result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")

    c.tags = [t for t in c.tags if t.id != tag_id]
    await db.commit()
    await db.refresh(c, ["tags"])
    return _contact_to_dict(c)
