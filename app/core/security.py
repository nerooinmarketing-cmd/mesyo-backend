"""
JWT token üretimi/doğrulaması ve şifre hashleme.
Supabase Auth KULLANMIYORUZ — kendi basit JWT sistemimiz var, çünkü
mevcut sistemde kullanıcılar telefon+şifre ile giriyor (email değil),
ve "superadmin / institution_admin / teacher" rolleri zaten institutions
tablosuna bağlı şekilde tasarlanmış (bkz. mesyo_soft_schema.sql).
"""
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str, institution_id: str | None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": user_id,
        "role": role,
        "institution_id": institution_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Geçersiz/süresi dolmuş token'da JWTError fırlatır — çağıran yer 401'e çevirmeli."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
