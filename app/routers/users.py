"""
Sistemdeki tüm kurum kullanıcılarını (institution_admin + teacher) superadmin
perspektifinden yönetir. Superadmin'in kendisi (role='superadmin') bu listede
görünmez — sadece kurumlara bağlı kullanıcılar.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.security import hash_password
from app.core.deps import require_role, CurrentUser

router = APIRouter(prefix="/users", tags=["users"])
_superadmin_only = require_role("superadmin")


class ResetPasswordRequest(BaseModel):
    new_password: str


class ToggleActiveRequest(BaseModel):
    is_active: bool


@router.get("")
def list_users(role_filter: str | None = None, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    q = (
        sb.table("users")
        .select("id, full_name, phone, role, is_active, last_login_at, created_at, institutions(name, slug)")
        .in_("role", ["institution_admin", "teacher"])
    )
    if role_filter:
        q = q.eq("role", role_filter)
    res = q.order("created_at", desc=True).execute()

    # institutions(name, slug) join'ini düzleştir
    result = []
    for row in res.data:
        inst = row.pop("institutions", None) or {}
        row["institution"] = inst.get("name", "")
        row["institution_slug"] = inst.get("slug", "")
        result.append(row)
    return result


@router.post("/{user_id}/toggle")
def toggle_user_active(user_id: str, body: ToggleActiveRequest, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    res = sb.table("users").update({"is_active": body.is_active}).eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")
    return res.data[0]


@router.post("/{user_id}/reset-password")
def reset_password(user_id: str, body: ResetPasswordRequest, current: CurrentUser = Depends(_superadmin_only)):
    if len(body.new_password) < 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Şifre en az 4 karakter olmalı")
    sb = get_supabase()
    res = (
        sb.table("users")
        .update({"password_hash": hash_password(body.new_password), "must_change_password": True})
        .eq("id", user_id).execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")
    return {"detail": "Şifre sıfırlandı"}


@router.delete("/{user_id}")
def delete_user(user_id: str, current: CurrentUser = Depends(_superadmin_only)):
    sb = get_supabase()
    res = sb.table("users").delete().eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")
    return {"detail": "Kullanıcı silindi"}
