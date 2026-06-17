"""
Auth endpoint'leri. Frontend lib/api.ts'teki authApi ile bire bir eşleşir:
  POST /auth/login            -> { token, user }
  GET  /auth/me                -> AuthUser
  POST /auth/change-password   -> 200 OK
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.security import verify_password, hash_password, create_access_token
from app.core.deps import get_current_user, CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    phone: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def _user_to_auth_user(row: dict) -> dict:
    """users tablosu satırını frontend'in AuthUser tipine çevirir."""
    institution = row.get("institutions")  # join ile gelirse
    return {
        "id": row["id"],
        "institution_id": row.get("institution_id"),
        "institution_slug": institution["slug"] if institution else None,
        "institution_name": institution["name"] if institution else None,
        "full_name": row["full_name"],
        "phone": row["phone"],
        "role": row["role"],
        "is_active": row["is_active"],
    }


@router.post("/login")
def login(body: LoginRequest):
    sb = get_supabase()
    res = (
        sb.table("users")
        .select("*, institutions(slug, name)")
        .eq("phone", body.phone)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telefon veya şifre hatalı")

    user_row = res.data[0]

    if not user_row.get("is_active", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hesabınız pasif durumda, kurum yöneticinizle iletişime geçin")

    if not user_row.get("password_hash") or not verify_password(body.password, user_row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telefon veya şifre hatalı")

    token = create_access_token(
        user_id=user_row["id"],
        role=user_row["role"],
        institution_id=user_row.get("institution_id"),
    )

    # Son giriş zamanını güncelle (sessiz başarısızlık — kritik değil)
    try:
        sb.table("users").update({"last_login_at": "now()"}).eq("id", user_row["id"]).execute()
    except Exception:
        pass

    return {"token": token, "user": _user_to_auth_user(user_row)}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)):
    sb = get_supabase()
    res = (
        sb.table("users")
        .select("*, institutions(slug, name)")
        .eq("id", current.id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")
    return _user_to_auth_user(res.data[0])


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, current: CurrentUser = Depends(get_current_user)):
    sb = get_supabase()
    res = sb.table("users").select("password_hash").eq("id", current.id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")

    if not verify_password(body.old_password, res.data[0]["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mevcut şifre hatalı")

    new_hash = hash_password(body.new_password)
    sb.table("users").update({
        "password_hash": new_hash,
        "must_change_password": False,
    }).eq("id", current.id).execute()

    return {"detail": "Şifre güncellendi"}
