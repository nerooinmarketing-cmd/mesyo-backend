"""
Her korumalı endpoint bu dependency'leri kullanır.
get_current_user: token'ı doğrular, kullanıcı bilgisini döner.
require_role(...): belirli rollere izin verir, diğerlerini 403 ile reddeder.

ÖNEMLİ — KURUM İZOLASYONU:
Supabase RLS'i service_role key ile bypass ettiğimiz için (bkz. core/supabase.py),
"bu kullanıcı sadece kendi kurumunun verisini görsün" kuralını burada,
Python tarafında biz uyguluyoruz. Her router, sorgularına
.eq("institution_id", current_user.institution_id) eklemeyi UNUTMAMALI.
Bu dosyadaki current_user nesnesi bu kontrolü yapacak yerlere institution_id sağlar.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from pydantic import BaseModel
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


class CurrentUser(BaseModel):
    id: str
    role: str  # 'superadmin' | 'institution_admin' | 'teacher'
    institution_id: str | None


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> CurrentUser:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Giriş yapılmamış")
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum süresi doldu veya geçersiz token")
    return CurrentUser(
        id=payload["sub"],
        role=payload["role"],
        institution_id=payload.get("institution_id"),
    )


def require_role(*allowed_roles: str):
    """Kullanım: Depends(require_role('superadmin', 'institution_admin'))"""
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok")
        return user
    return _check


def require_institution(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """institution_admin veya teacher — yani bir kuruma bağlı olmalı, superadmin değil."""
    if user.institution_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem bir kuruma bağlı kullanıcı gerektirir")
    return user
