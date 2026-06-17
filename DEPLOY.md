# Mesyo Soft Backend — Hetzner Kurulum Talimatları

## 1. Supabase bilgilerini al
Supabase Dashboard → Project Settings → API:
- `Project URL` → `SUPABASE_URL`
- `service_role` key (⚠️ `anon` key DEĞİL — service_role, RLS'i bypass eder, gizli tutulmalı) → `SUPABASE_SERVICE_KEY`

## 2. Dosyaları sunucuya kopyala
Bu klasörün tamamını (mesyo-backend/) Hetzner sunucunuzdaki `/opt/mesyo-backend` dizinine SCP ile atın:

```bash
scp -r mesyo-backend root@91.98.129.128:/opt/
```

## 3. Sunucuda Python ortamı kur
```bash
ssh root@91.98.129.128
cd /opt/mesyo-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 4. .env dosyasını oluştur
```bash
cp .env.example .env
nano .env
```
İçine gerçek `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` ve rastgele bir `JWT_SECRET` yazın.
JWT_SECRET üretmek için:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 5. İlk superadmin kullanıcısını oluştur
Supabase SQL Editor'de (mesyo_soft_schema.sql çalıştırıldıktan SONRA):

```sql
-- Önce şifrenin bcrypt hash'ini üretin (sunucuda):
-- python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('sizin-sifreniz'))"

insert into users (full_name, phone, role, password_hash, is_active)
values ('Şenol Bey', '05XXXXXXXXX', 'superadmin', '<yukarıdaki komuttan çıkan hash>', true);
```

## 6. Systemd servisi kur
```bash
cp mesyo-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mesyo-backend
systemctl start mesyo-backend
systemctl status mesyo-backend   # "active (running)" görmelisiniz
```

## 7. Test et
```bash
curl http://localhost:8200/health
# {"status":"ok"} dönmeli

curl -X POST http://localhost:8200/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"05XXXXXXXXX","password":"sizin-sifreniz"}'
# {"token":"...","user":{...}} dönmeli
```

## 8. Nginx reverse proxy (eğer dışarıdan HTTPS ile erişilecekse)
Sizin diğer projelerinizde kullandığınız kalıba uygun örnek:

```nginx
location /api {
    proxy_pass http://localhost:8200;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 9. Frontend'i bağla
`mesyo-system/.env` dosyasındaki `VITE_API_URL` zaten `http://91.98.129.128:8200/api` olarak
tanımlı — değiştirmenize gerek yok, backend ayakta olduğu anda frontend otomatik bağlanacak.

## Loglara bakmak için
```bash
journalctl -u mesyo-backend -f
```

## Güncelleme yaparken
```bash
cd /opt/mesyo-backend
# yeni dosyaları kopyaladıktan sonra:
systemctl restart mesyo-backend
```
