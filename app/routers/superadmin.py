"""
Superadmin endpoint'leri — sadece role='superadmin' erişebilir.
createInstitution burada DOĞRUDAN kurum açar (önceki onboarding akışından farklı
olarak başvuru/onay sürecini atlar — superadmin'in elle yeni kurum eklediği durum).

Başvuru onay akışı (institution_applications -> approve) için SQL şemasındaki
approve_institution_application() fonksiyonunu burada RPC ile çağırıyoruz —
mantığı iki kere yazmamak için.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.security import hash_password, create_access_token
from app.core.deps import require_role, CurrentUser

router = APIRouter(prefix="/superadmin", tags=["superadmin"])

_superadmin_only = require_role("superadmin")


class CreateInstitutionRequest(BaseModel):
    name: str
    slug: str
    city: str = "Konya"
    district: str
    address: str | None = None
    responsible_name: str
    responsible_phone: str
    email: str | None = None
    student_limit: int = 150
    subscription_status: str = "trial"
    admin_phone: str
    admin_password: str


class UpdateInstitutionRequest(BaseModel):
    name: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    responsible_name: str | None = None
    responsible_phone: str | None = None
    email: str | None = None


class ToggleActiveRequest(BaseModel):
    is_active: bool


class SetSubscriptionRequest(BaseModel):
    status: str
    expires_at: str | None = None


@router.get("/stats")
def stats(current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    institutions = sb.table("institutions").select("id, is_active, subscription_status").execute().data
    students = sb.table("students").select("id", count="exact").eq("status", "approved").execute()
    pending_apps = sb.table("institution_applications").select("id", count="exact").eq("status", "pending").execute()
    pending_payments = sb.table("subscription_payments").select("id", count="exact").eq("status", "pending").execute()

    return {
        "total_institutions": len(institutions),
        "active_institutions": sum(1 for i in institutions if i["is_active"]),
        "trial_institutions": sum(1 for i in institutions if i["subscription_status"] == "trial"),
        "total_students": students.count or 0,
        "pending_applications": pending_apps.count or 0,
        "pending_payments": pending_payments.count or 0,
    }


@router.get("/institutions")
def list_institutions(
    search: str | None = None,
    status_filter: str | None = None,
    city: str | None = None,
    current: CurrentUser = Depends(_superadmin_only),
):
    sb = get_supabase()
    q = sb.table("institutions").select("*")
    if search:
        q = q.ilike("name", f"%{search}%")
    if status_filter:
        q = q.eq("subscription_status", status_filter)
    if city:
        q = q.eq("city", city)
    res = q.order("created_at", desc=True).execute()
    return res.data


@router.get("/institutions/{institution_id}")
def get_institution(institution_id: str, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    res = sb.table("institutions").select("*").eq("id", institution_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.post("/institutions")
def create_institution(body: CreateInstitutionRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()

    slug_check = sb.table("institutions").select("id").eq("slug", body.slug).limit(1).execute()
    if slug_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu slug zaten kullanılıyor")

    inst_data = body.model_dump(exclude={"admin_phone", "admin_password"})
    inst_res = sb.table("institutions").insert(inst_data).execute()
    institution = inst_res.data[0]

    # institutions insert tetikleyicisi (trigger) otomatik olarak:
    # - varsayılan modülleri atar (assign_default_modules)
    # - "Ana Kasa" açar (create_default_cash_register)
    # bkz. mesyo_soft_schema.sql

    sb.table("users").insert({
        "institution_id": institution["id"],
        "full_name": body.responsible_name,
        "phone": body.admin_phone,
        "password_hash": hash_password(body.admin_password),
        "role": "institution_admin",
        "must_change_password": True,
    }).execute()

    return institution


@router.patch("/institutions/{institution_id}")
def update_institution(institution_id: str, body: UpdateInstitutionRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")
    res = sb.table("institutions").update(data).eq("id", institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.post("/institutions/{institution_id}/toggle")
def toggle_active(institution_id: str, body: ToggleActiveRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    res = sb.table("institutions").update({"is_active": body.is_active}).eq("id", institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.post("/institutions/{institution_id}/subscription")
def set_subscription(institution_id: str, body: SetSubscriptionRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    data = {"subscription_status": body.status}
    if body.expires_at:
        data["subscription_expires_at"] = body.expires_at
    res = sb.table("institutions").update(data).eq("id", institution_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurum bulunamadı")
    return res.data[0]


@router.get("/institutions/{institution_id}/students")
def institution_students(institution_id: str, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    res = sb.table("students").select("*").eq("institution_id", institution_id).execute()
    return res.data


@router.get("/institutions/{institution_id}/teachers")
def institution_teachers(institution_id: str, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    res = sb.table("users").select("*").eq("institution_id", institution_id).eq("role", "teacher").execute()
    return res.data


@router.post("/impersonate/{institution_id}")
def impersonate(institution_id: str, current: CurrentUser = Depends(_superadmin_only)):
    """Superadmin'in bir kurumun yöneticisi gibi giriş yapmasını sağlar (destek amaçlı)."""
    sb = get_supabase()
    admin_res = (
        sb.table("users").select("*")
        .eq("institution_id", institution_id).eq("role", "institution_admin")
        .limit(1).execute()
    )
    if not admin_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu kurumun bir yöneticisi yok")

    admin = admin_res.data[0]
    token = create_access_token(user_id=admin["id"], role="institution_admin", institution_id=institution_id)

    inst_res = sb.table("institutions").select("slug, name").eq("id", institution_id).limit(1).execute()
    inst = inst_res.data[0] if inst_res.data else {}

    return {
        "token": token,
        "user": {
            "id": admin["id"],
            "institution_id": institution_id,
            "institution_slug": inst.get("slug"),
            "institution_name": inst.get("name"),
            "full_name": admin["full_name"],
            "phone": admin["phone"],
            "role": "institution_admin",
            "is_active": admin["is_active"],
        },
    }


@router.get("/settings")
def get_settings(_: CurrentUser = Depends(require_superadmin)):
    sb = get_supabase()
    res = sb.table("system_settings").select("key,value").execute()
    return res.data or []


@router.post("/settings")
def save_settings(body: list, _: CurrentUser = Depends(require_superadmin)):
    sb = get_supabase()
    for item in body:
        sb.table("system_settings").upsert(
            {"key": item["key"], "value": item["value"], "updated_at": "now()"},
            on_conflict="key"
        ).execute()
    return {"detail": "Kaydedildi"}


@router.get("/settings/public")
def get_public_settings():
    """Kurumların erişebileceği ödeme bilgileri"""
    sb = get_supabase()
    res = sb.table("system_settings").select("key,value").in_("key", [
        "payment_iban", "payment_bank", "payment_name", "payment_amount", "payment_note"
    ]).execute()
    return {item["key"]: item["value"] for item in (res.data or [])}


@router.delete("/institutions/{institution_id}")
def delete_institution(institution_id: str, _: CurrentUser = Depends(require_role("superadmin"))):
    sb = get_supabase()
    sb.table("institutions").delete().eq("id", institution_id).execute()
    return {"detail": "Kurum silindi"}


@router.delete("/applications/{application_id}")
def delete_application(application_id: str, _: CurrentUser = Depends(require_role("superadmin"))):
    sb = get_supabase()
    sb.table("institution_applications").delete().eq("id", application_id).execute()
    return {"detail": "Başvuru silindi"}
