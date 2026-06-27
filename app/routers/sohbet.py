"""
Sohbet modülü — Sohbet takvimi, kayıt ve arşiv yönetimi.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/sohbet", tags=["sohbet"])


# ── MODELLER ──────────────────────────────────────────────────────────────────

class SohbetCreate(BaseModel):
    title: str
    topic: str | None = None
    location: str | None = None
    event_date: str
    event_time: str


class KayitCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    meslek: str | None = None
    katiliyor: bool = True


# ── ADMIN: SOHBET YÖNETİMİ ───────────────────────────────────────────────────

@router.get("/list")
def list_sohbets(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("sohbets")
        .select("*")
        .eq("institution_id", current.institution_id)
        .order("event_date", desc=True)
        .execute()
    )
    # Her sohbet için kayıt sayısını ekle
    result = []
    for s in res.data:
        count_res = sb.table("sohbet_kayitlar").select("id", count="exact").eq("sohbet_id", s["id"]).eq("katiliyor", True).execute()
        s["kayit_count"] = count_res.count or 0
        result.append(s)
    return result


@router.post("/list")
def create_sohbet(body: SohbetCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("sohbets").insert({
        "institution_id": current.institution_id,
        "title": body.title,
        "topic": body.topic,
        "location": body.location,
        "event_date": body.event_date,
        "event_time": body.event_time,
        "created_by": current.id,
    }).execute()
    return res.data[0]


@router.delete("/list/{sohbet_id}")
def delete_sohbet(sohbet_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    sb.table("sohbets").delete().eq("id", sohbet_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}


@router.get("/list/{sohbet_id}/kayitlar")
def get_kayitlar(sohbet_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Sohbetin bu kuruma ait olduğunu doğrula
    sohbet_check = sb.table("sohbets").select("id").eq("id", sohbet_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not sohbet_check.data:
        return []
    res = (
        sb.table("sohbet_kayitlar")
        .select("*")
        .eq("sohbet_id", sohbet_id)
        .order("created_at")
        .execute()
    )
    return res.data


# ── ARŞİV ─────────────────────────────────────────────────────────────────────

@router.get("/arsiv")
def get_arsiv(current: CurrentUser = Depends(require_institution)):
    """Kurumun kümülatif sohbet katılımcı arşivi."""
    sb = get_supabase()
    res = (
        sb.table("sohbet_arsiv")
        .select("*")
        .eq("institution_id", current.institution_id)
        .order("katilim_count", desc=True)
        .execute()
    )
    return res.data


# ── PUBLIC: KAYIT FORMU ───────────────────────────────────────────────────────

@router.get("/public/{sohbet_id}")
def get_sohbet_public(sohbet_id: str):
    """Kayıt formu için sohbet bilgileri."""
    sb = get_supabase()
    res = sb.table("sohbets").select("id,title,topic,location,event_date,event_time,institution_id").eq("id", sohbet_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sohbet bulunamadı")
    return res.data[0]


@router.post("/public/{sohbet_id}/kayit")
def kayit_ol(sohbet_id: str, body: KayitCreate):
    """Sohbete kayıt ol — arşive de ekle/güncelle."""
    sb = get_supabase()

    # Sohbeti bul
    sohbet_res = sb.table("sohbets").select("institution_id").eq("id", sohbet_id).limit(1).execute()
    if not sohbet_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sohbet bulunamadı")
    institution_id = sohbet_res.data[0]["institution_id"]

    # Daha önce kayıt var mı?
    existing = sb.table("sohbet_kayitlar").select("id").eq("sohbet_id", sohbet_id).eq("phone", body.phone).limit(1).execute()
    if existing.data:
        # Güncelle
        sb.table("sohbet_kayitlar").update({"katiliyor": body.katiliyor}).eq("id", existing.data[0]["id"]).execute()
        return {"message": "Kayıt güncellendi", "already_registered": True}

    # Yeni kayıt
    sb.table("sohbet_kayitlar").insert({
        "sohbet_id": sohbet_id,
        "institution_id": institution_id,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "phone": body.phone,
        "meslek": body.meslek,
        "katiliyor": body.katiliyor,
    }).execute()

    # Arşive ekle veya güncelle (upsert)
    if body.katiliyor:
        arsiv_existing = sb.table("sohbet_arsiv").select("id,katilim_count").eq("institution_id", institution_id).eq("phone", body.phone).limit(1).execute()
        if arsiv_existing.data:
            sb.table("sohbet_arsiv").update({
                "last_seen_at": "now()",
                "katilim_count": arsiv_existing.data[0]["katilim_count"] + 1,
                "first_name": body.first_name,
                "last_name": body.last_name,
                "meslek": body.meslek,
            }).eq("id", arsiv_existing.data[0]["id"]).execute()
        else:
            sb.table("sohbet_arsiv").insert({
                "institution_id": institution_id,
                "first_name": body.first_name,
                "last_name": body.last_name,
                "phone": body.phone,
                "meslek": body.meslek,
            }).execute()

    return {"message": "Kayıt tamamlandı", "already_registered": False}
