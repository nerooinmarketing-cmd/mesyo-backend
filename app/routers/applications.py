"""
Kurum başvuruları. Onaylama/reddetme mantığının ağır kısmı (kurum + admin
kullanıcı oluşturma, geçici şifre üretme, atomiklik) SQL fonksiyonlarında
(approve_institution_application, reject_institution_application) — burada
sadece bu RPC'leri çağırıyoruz, mantığı tekrar yazmıyoruz.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_role, CurrentUser

router = APIRouter(prefix="/applications", tags=["applications"])
_superadmin_only = require_role("superadmin")


class ApproveRequest(BaseModel):
    final_slug: str


class RejectRequest(BaseModel):
    reason: str | None = None


@router.get("")
def list_applications(status_filter: str | None = None, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    q = sb.table("institution_applications").select("*")
    if status_filter:
        q = q.eq("status", status_filter)
    res = q.order("created_at", desc=True).execute()
    return res.data


@router.post("/{application_id}/approve")
def approve_application(application_id: str, body: ApproveRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    try:
        res = sb.rpc("approve_institution_application", {
            "p_application_id": application_id,
            "p_final_slug": body.final_slug,
            "p_reviewed_by": current.id,
        }).execute()
    except Exception as e:
        # SQL fonksiyonu "raise exception" ile hata verirse (slug çakışması, zaten işlenmiş vb.)
        # buraya düşer — mesajı olduğu gibi kullanıcıya iletiyoruz.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    if not res.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Onaylama işlemi başarısız oldu")

    row = res.data[0]
    return {"institution_id": row["institution_id"], "temp_password": row["temp_password"]}


@router.post("/{application_id}/reject")
def reject_application(application_id: str, body: RejectRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    try:
        sb.rpc("reject_institution_application", {
            "p_application_id": application_id,
            "p_reason": body.reason,
            "p_reviewed_by": current.id,
        }).execute()
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return {"detail": "Başvuru reddedildi"}
