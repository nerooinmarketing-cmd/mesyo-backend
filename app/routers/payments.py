"""
Abonelik ödemeleri. list_payments çağrıldığında vadesi geçmiş ama hâlâ
'pending' olan kayıtları otomatik 'overdue'ya çeviriyoruz — ayrı bir cron
job kurmaya gerek kalmıyor, her sayfa açılışında kendiliğinden günceller.
"""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_role, CurrentUser

router = APIRouter(prefix="/payments", tags=["payments"])
_superadmin_only = require_role("superadmin")


class ConfirmPaymentRequest(BaseModel):
    extend_one_year: bool = True


@router.get("")
def list_payments(status_filter: str | None = None, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()

    # Vadesi geçmiş ama hâlâ pending olan kayıtları overdue'ya çevir (lazy update)
    today = date.today().isoformat()
    sb.table("subscription_payments").update({"status": "overdue"}).eq("status", "pending").lt(
        "due_date", today
    ).execute()

    q = (
        sb.table("subscription_payments")
        .select("*, institutions(name, responsible_phone)")
    )
    if status_filter:
        q = q.eq("status", status_filter)
    res = q.order("due_date").execute()

    # institutions(name, responsible_phone) join'ini düzleştir — frontend institution_name/responsible_phone bekliyor
    result = []
    for row in res.data:
        inst = row.pop("institutions", None) or {}
        row["institution_name"] = inst.get("name", "")
        row["responsible_phone"] = inst.get("responsible_phone", "")
        result.append(row)
    return result


@router.post("/{payment_id}/confirm")
def confirm_payment(payment_id: str, body: ConfirmPaymentRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()

    payment_res = sb.table("subscription_payments").select("*, institutions(id)").eq("id", payment_id).execute()
    if not payment_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme kaydı bulunamadı")
    payment = payment_res.data[0]

    sb.table("subscription_payments").update({
        "status": "paid",
        "paid_at": date.today().isoformat(),
        "confirmed_by": current.id,
    }).eq("id", payment_id).execute()

    if body.extend_one_year:
        institution_id = payment["institutions"]["id"]
        new_expiry = (date.today() + timedelta(days=365)).isoformat()
        sb.table("institutions").update({
            "subscription_status": "active",
            "subscription_expires_at": new_expiry,
        }).eq("id", institution_id).execute()

    return {"detail": "Ödeme onaylandı"}
