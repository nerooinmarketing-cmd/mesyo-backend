"""
Supabase client. service_role key kullanır — bu, RLS politikalarını bypass eder.
Bu YÜZDEN tüm yetkilendirme/izolasyon kontrolünü (hangi kurum, hangi rol)
burada, backend kodunda BİZ yapıyoruz; veritabanına güvenmiyoruz.
service_role key ASLA frontend'e veya herhangi bir herkese açık yere sızdırılmamalı.
"""
from supabase import create_client, Client
from app.core.config import settings

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError(
                "SUPABASE_URL ve SUPABASE_SERVICE_KEY .env dosyasında tanımlı değil. "
                "Supabase Dashboard > Project Settings > API'den alıp .env dosyasına ekleyin."
            )
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client
