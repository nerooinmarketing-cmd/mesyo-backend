"""
Login gerektirmeyen public endpoint'ler — kayıt formları buraya yazar.
KVKK onayı veritabanı seviyesinde de zorunlu (bkz. mesyo_soft_schema.sql RLS politikaları),
ama burada da kontrol ediyoruz ki kullanıcıya anlamlı bir hata mesajı dönelim.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase

router = APIRouter(prefix="/public", tags=["public"])


class PublicRegisterRequest(BaseModel):
    first_name: str
    last_name: str
    birth_date: str
    gender: str
    tc_no: str | None = None
    city: str | None = "Konya"
    district: str | None = "Meram"
    mahalle: str
    sokak: str | None = None
    address: str | None = None
    parent_first_name: str
    parent_last_name: str
    parent_phone: str
    parent_phone2: str | None = None
    notes: str | None = None
    kvkk: bool


class InstitutionApplicationRequest(BaseModel):
    name: str
    city: str = "Konya"
    district: str
    address: str | None = None
    responsible_name: str
    responsible_phone: str
    email: str | None = None
    student_count_estimate: str | None = None
    note: str | None = None
    kvkk: bool


@router.post("/institution-applications")
def submit_institution_application(body: InstitutionApplicationRequest):
    """Kurum/cami başvuru formu — herkese açık, oturum gerekmez.
    Superadmin'in Başvurular sayfası bu tabloyu okur."""
    if not body.kvkk:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "KVKK onayı zorunludur")

    sb = get_supabase()
    data = body.model_dump(exclude={"kvkk"})
    data["kvkk_consent"] = True

    from datetime import datetime, timezone
    data["kvkk_consent_at"] = datetime.now(timezone.utc).isoformat()

    res = sb.table("institution_applications").insert(data).execute()
    return res.data[0]


@router.get("/institution/{slug}")
def institution_by_slug(slug: str):
    sb = get_supabase()
    res = (
        sb.table("institutions")
        .select("id, name, city, district, is_active, allowed_districts, allowed_mahalles")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    if not res.data[0]["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu kurumun paneli şu anda aktif değil")
    return res.data[0]


@router.post("/register/{slug}")
def public_register(slug: str, body: PublicRegisterRequest):
    if not body.kvkk:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "KVKK onayı zorunludur")

    sb = get_supabase()

    inst_res = sb.table("institutions").select("id").eq("slug", slug).limit(1).execute()
    if not inst_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    institution_id = inst_res.data[0]["id"]

    season_res = (
        sb.table("seasons")
        .select("id")
        .eq("institution_id", institution_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not season_res.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu kurumun aktif bir sezonu yok, lütfen kurum ile iletişime geçin")
    season_id = season_res.data[0]["id"]

    data = body.model_dump(exclude={"kvkk"})
    data["institution_id"] = institution_id
    data["season_id"] = season_id
    data["status"] = "pending"
    data["registration_source"] = "form"
    data["kvkk_consent"] = True

    res = sb.table("students").insert(data).execute()
    return res.data[0]
