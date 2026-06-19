"""
institution_admin'in kendi kurumuyla ilgili işlemleri (kurum bilgisi düzenleme,
dashboard istatistikleri). Diğer kurumlara erişim yok — require_institution
zaten current.institution_id'yi token'dan alıyor, frontend'in başka bir
institution_id göndermesi mümkün değil.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/institution", tags=["institution"])


class InstitutionUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    responsible_name: str | None = None
    responsible_phone: str | None = None
    email: str | None = None
    wa_group_link: str | None = None


@router.get("/me")
def me(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("institutions").select("*").eq("id", current.institution_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.patch("/me")
def update_me(body: InstitutionUpdate, current: CurrentUser = Depends(require_institution)):
    if current.role != "institution_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sadece kurum yöneticisi düzenleyebilir")
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")
    res = sb.table("institutions").update(data).eq("id", current.institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.get("/stats")
def stats(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    inst_id = current.institution_id

    students = sb.table("students").select("id, status, gender").eq("institution_id", inst_id).execute().data
    classrooms = sb.table("classrooms").select("id", count="exact").eq("institution_id", inst_id).execute()
    teachers = sb.table("users").select("id", count="exact").eq("institution_id", inst_id).eq("role", "teacher").execute()

    approved = [s for s in students if s["status"] == "approved"]

    return {
        "total_students": len(approved),
        "pending_students": sum(1 for s in students if s["status"] == "pending"),
        "erkek_count": sum(1 for s in approved if s["gender"] == "erkek"),
        "kiz_count": sum(1 for s in approved if s["gender"] == "kiz"),
        "classroom_count": classrooms.count or 0,
        "teacher_count": teachers.count or 0,
    }


class AddressSettings(BaseModel):
    allowed_districts: list[str] = []
    allowed_mahalles: list[str] = []


@router.get("/settings/address")
def get_address_settings(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("institutions")
        .select("allowed_districts, allowed_mahalles, city, district")
        .eq("id", current.institution_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.patch("/settings/address")
def update_address_settings(body: AddressSettings, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("institutions")
        .update({
            "allowed_districts": body.allowed_districts,
            "allowed_mahalles": body.allowed_mahalles,
        })
        .eq("id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return {"detail": "Güncellendi", "allowed_districts": body.allowed_districts, "allowed_mahalles": body.allowed_mahalles}
