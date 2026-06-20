"""
Ön Muhasebe — Kasalar ve Gelir/Gider kayıtları.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser
import uuid

router = APIRouter(prefix="/accounting", tags=["accounting"])


# ── MODELLER ──────────────────────────────────────────────────────────────────

class KasaCreate(BaseModel):
    name: str
    color: str = "green"
    note: str | None = None


class KasaUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    note: str | None = None


class EntryCreate(BaseModel):
    cash_register_id: str
    to_cash_register_id: str | None = None
    entry_type: str               # gelir | gider | transfer
    category: str = "diger"
    amount: float
    description: str
    donor_name: str | None = None
    entry_date: str
    note: str | None = None
    receipt_url: str | None = None


class EntryUpdate(BaseModel):
    description: str | None = None
    note: str | None = None
    amount: float | None = None
    entry_date: str | None = None
    donor_name: str | None = None
    category: str | None = None


# ── KASALAR ───────────────────────────────────────────────────────────────────

@router.get("/registers")
def list_registers(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("cash_registers").select("*").eq("institution_id", current.institution_id).order("created_at").execute()
    return res.data


@router.post("/registers")
def create_register(body: KasaCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("cash_registers").insert({
        "institution_id": current.institution_id,
        "name": body.name,
        "color": body.color,
        "note": body.note,
    }).execute()
    return res.data[0]


@router.patch("/registers/{register_id}")
def update_register(register_id: str, body: KasaUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")
    res = sb.table("cash_registers").update(data).eq("id", register_id).eq("institution_id", current.institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kasa bulunamadı")
    return res.data[0]


@router.delete("/registers/{register_id}")
def delete_register(register_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Kasaya ait hareket var mı kontrol et
    entries = sb.table("accounting_entries").select("id").eq("cash_register_id", register_id).limit(1).execute()
    if entries.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu kasaya ait hareketler var, önce hareketleri silin.")
    sb.table("cash_registers").delete().eq("id", register_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}


# ── HAREKETLER ────────────────────────────────────────────────────────────────

@router.get("/entries")
def list_entries(
    start: str | None = None,
    end: str | None = None,
    register_id: str | None = None,
    current: CurrentUser = Depends(require_institution),
):
    sb = get_supabase()
    q = sb.table("accounting_entries").select("*").eq("institution_id", current.institution_id)
    if start:
        q = q.gte("entry_date", start)
    if end:
        q = q.lte("entry_date", end)
    if register_id:
        q = q.eq("cash_register_id", register_id)
    res = q.order("entry_date", desc=True).order("created_at", desc=True).execute()
    return res.data


@router.post("/entries")
def create_entry(body: EntryCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Kasa bu kuruma ait mi?
    reg = sb.table("cash_registers").select("id").eq("id", body.cash_register_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not reg.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kasa bulunamadı")
    res = sb.table("accounting_entries").insert({
        "institution_id": current.institution_id,
        "cash_register_id": body.cash_register_id,
        "to_cash_register_id": body.to_cash_register_id,
        "entry_type": body.entry_type,
        "category": body.category,
        "amount": body.amount,
        "description": body.description,
        "donor_name": body.donor_name,
        "entry_date": body.entry_date,
        "note": body.note,
        "receipt_url": body.receipt_url,
        "created_by": current.id,
    }).execute()
    return res.data[0]


@router.post("/entries/{entry_id}/receipt")
async def upload_receipt(
    entry_id: str,
    file: UploadFile = File(...),
    current: CurrentUser = Depends(require_institution),
):
    """Fiş/makbuz fotoğrafı yükle."""
    sb = get_supabase()
    # Entry bu kuruma ait mi?
    entry = sb.table("accounting_entries").select("id").eq("id", entry_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not entry.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hareket bulunamadı")

    # Dosyayı oku
    contents = await file.read()
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    file_name = f"receipts/{current.institution_id}/{entry_id}.{ext}"

    try:
        # Supabase Storage'a yükle
        sb.storage.from_("accounting").upload(
            path=file_name,
            file=contents,
            file_options={"content-type": file.content_type or "image/jpeg", "upsert": "true"}
        )
        # Public URL al
        url_res = sb.storage.from_("accounting").get_public_url(file_name)
        receipt_url = url_res if isinstance(url_res, str) else url_res.get("publicUrl", "")
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Dosya yükleme hatası: {str(e)}")

    # Entry'yi güncelle
    sb.table("accounting_entries").update({"receipt_url": receipt_url}).eq("id", entry_id).execute()
    return {"receipt_url": receipt_url}


@router.patch("/entries/{entry_id}")
def update_entry(entry_id: str, body: EntryUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")
    res = sb.table("accounting_entries").update(data).eq("id", entry_id).eq("institution_id", current.institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hareket bulunamadı")
    return res.data[0]


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("accounting_entries").delete().eq("id", entry_id).eq("institution_id", current.institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hareket bulunamadı")
    return {"detail": "Silindi"}
