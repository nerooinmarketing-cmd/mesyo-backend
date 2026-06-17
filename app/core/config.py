"""
Uygulama ayarları. Tüm gizli/ortam-bağımlı değerler buradan okunur.
Hetzner'e deploy ederken bu değerleri .env dosyasına yazın, kodu değiştirmeyin.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase proje ayarları (Supabase Dashboard > Project Settings > API'den alınır)
    supabase_url: str = ""
    supabase_service_key: str = ""  # service_role key — RLS'i bypass eder, SADECE backend'de kullanılır

    # JWT ayarları — kendi auth sistemimiz için (Supabase Auth değil, manuel JWT)
    jwt_secret: str = "DEGISTIRIN-bu-cok-onemli-uzun-rastgele-bir-deger-olmali"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24 * 7  # 7 gün

    # CORS — frontend'in çalıştığı adresler
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://178.105.184.196",
        "https://mesyosoft.com.tr",
        "https://www.mesyosoft.com.tr",
        "https://*.mesyosoft.com.tr",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
