"""
Bilge Kervan — Aile yolculuk oyunu
Yaz kursu: 6 hafta (Konya → Mekke arası 6 durak)
Yıllık kurs: 12 ay (Konya → Mekke arası 11 durak)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser
from datetime import date

router = APIRouter(prefix="/kervan", tags=["kervan"])

# ── YOL HARİTALARI ────────────────────────────────────────────────────────────

YAZ_ROTA = [
    {"sehir": "Konya",   "hedef": 50,  "hikaye": "Mevlana'nın şehri. Yolculuk buradan başlar. Sabır ve sevgi öğrenilir."},
    {"sehir": "Kayseri", "hedef": 50,  "hikaye": "Ahilik geleneğinin kalbi. Dürüstlük ve helal kazanç bu şehirde öğrenildi."},
    {"sehir": "Urfa",    "hedef": 50,  "hikaye": "Hz. İbrahim'in şehri. Balıklı göl ve sabır ile imtihanın yurdu."},
    {"sehir": "Şam",     "hedef": 50,  "hikaye": "Hz. Bilal burada doğdu. İlk Müslümanların şehri, sabır ve iman yurdu."},
    {"sehir": "Medine",  "hedef": 50,  "hikaye": "Hz. Peygamberin şehri. Huzur, sevgi ve müjdenin kalbi."},
    {"sehir": "Mekke",   "hedef": 50,  "hikaye": "⭐ Kabe'nin şehri. Yolculuğun sonu, duanın başlangıcı."},
]

YILLIK_ROTA = [
    {"sehir": "Konya",    "hedef": 120, "hikaye": "Mevlana'nın şehri. Yolculuk buradan başlar."},
    {"sehir": "Aksaray",  "hedef": 120, "hikaye": "İpek Yolu'nun kavşağı. Kervanlar burada dinlenirdi."},
    {"sehir": "Kayseri",  "hedef": 120, "hikaye": "Ahilik geleneğinin kalbi. Dürüstlük ve ticaret şehri."},
    {"sehir": "Mardin",   "hedef": 120, "hikaye": "Taş evlerin şehri. Farklı inançlar bir arada yaşadı."},
    {"sehir": "Urfa",     "hedef": 120, "hikaye": "Hz. İbrahim'in şehri. Balıklı göl ve sabır."},
    {"sehir": "Antakya",  "hedef": 120, "hikaye": "Hz. Lut'un yurdu. Tarihin kokladığı kadim şehir."},
    {"sehir": "Halep",    "hedef": 120, "hikaye": "Büyük alimler bu şehirde yetişti. İlim merkezi."},
    {"sehir": "Şam",      "hedef": 120, "hikaye": "Hz. Bilal burada doğdu. İslam'ın ilk şehirlerinden."},
    {"sehir": "Amman",    "hedef": 120, "hikaye": "Çöl kapısı. Mekke'ye son büyük durak."},
    {"sehir": "Medine",   "hedef": 120, "hikaye": "Hz. Peygamberin şehri. Huzur ve müjde."},
    {"sehir": "Mekke",    "hedef": 120, "hikaye": "⭐ Kabe'nin şehri. Yolculuğun sonu, duanın başlangıcı."},
]

# ── SORU BANKASI (Yaş grubuna göre) ──────────────────────────────────────────

SORU_BANKASI = {
    "7-8": {
        "cocuk": [
            {"konu": "Fatiha Suresi", "soru": "Fatiha Suresi kaç ayetten oluşur?", "a": "5", "b": "6", "c": "7", "d": "8", "dogru": "c"},
            {"konu": "Namaz", "soru": "Günde kaç vakit namaz kılınır?", "a": "3", "b": "4", "c": "5", "d": "6", "dogru": "c"},
            {"konu": "Bismillah", "soru": "Bismillah ne zaman söylenir?", "a": "Sadece namazda", "b": "Her işin başında", "c": "Yemekten önce", "d": "Uyumadan önce", "dogru": "b"},
            {"konu": "İhlas Suresi", "soru": "İhlas Suresi kaç ayettir?", "a": "3", "b": "4", "c": "5", "d": "6", "dogru": "b"},
            {"konu": "Kelime-i Tevhid", "soru": "Kelime-i Tevhid ne ile başlar?", "a": "Elhamdülillah", "b": "Bismillah", "c": "La ilahe", "d": "Allahüekber", "dogru": "c"},
            {"konu": "Oruç", "soru": "Oruç hangi ayda tutulur?", "a": "Şaban", "b": "Ramazan", "c": "Muharrem", "d": "Recep", "dogru": "b"},
            {"konu": "Hz. Adem", "soru": "Hz. Adem kimdir?", "a": "İlk peygamber", "b": "Son peygamber", "c": "İlk cami", "d": "İlk kitap", "dogru": "a"},
            {"konu": "Kabe", "soru": "Kabe hangi şehirdedir?", "a": "Medine", "b": "Şam", "c": "Mekke", "d": "Kudüs", "dogru": "c"},
        ],
        "veli": [
            {"soru": "Fatiha Suresi namazda kaç rekatte okunur?", "a": "Sadece sabah namazında", "b": "Her rekatte", "c": "Sadece ilk rekatte", "d": "Son rekatte", "dogru": "b"},
            {"soru": "Bismillah'ın Türkçe anlamı nedir?", "a": "Allah'a sığınırım", "b": "Allah'a hamdolsun", "c": "Allah'ın adıyla", "d": "Allah büyüktür", "dogru": "c"},
            {"soru": "İhlas Suresi ne hakkındadır?", "a": "Sabır", "b": "Allah'ın birliği", "c": "Namaz", "d": "Oruç", "dogru": "b"},
            {"soru": "Kelime-i Tevhid'in anlamı nedir?", "a": "Allah büyüktür", "b": "Allah'tan başka ilah yoktur", "c": "Hamd Allah'a", "d": "Allah affedicidir", "dogru": "b"},
        ]
    },
    "9-10": {
        "cocuk": [
            {"konu": "Kuran", "soru": "Kuran-ı Kerim kaç yılda tamamlandı?", "a": "10 yıl", "b": "20 yıl", "c": "23 yıl", "d": "30 yıl", "dogru": "c"},
            {"konu": "5 Şart", "soru": "İslam'ın 5 şartından hangisi doğrudur?", "a": "Kelime-i Şehadet, Namaz, Oruç, Zekat, Hac", "b": "Namaz, Oruç, Zekat, Hac, Cihad", "c": "Kelime-i Şehadet, Namaz, Oruç, Sadaka, Hac", "d": "Namaz, Oruç, Hac, Cihad, Dua", "dogru": "a"},
            {"konu": "Hz. Musa", "soru": "Hz. Musa'ya hangi kitap verildi?", "a": "İncil", "b": "Zebur", "c": "Tevrat", "d": "Kuran", "dogru": "c"},
            {"konu": "Namaz", "soru": "Sabah namazı kaç rekattir?", "a": "2", "b": "3", "c": "4", "d": "5", "dogru": "a"},
            {"konu": "Zekat", "soru": "Zekat kime verilmez?", "a": "Fakirlere", "b": "Zenginlere", "c": "Yolculara", "d": "Borçlulara", "dogru": "b"},
            {"konu": "Hz. Peygamber", "soru": "Hz. Muhammed (sav) kaç yaşında peygamber oldu?", "a": "35", "b": "40", "c": "45", "d": "50", "dogru": "b"},
            {"konu": "Kıble", "soru": "Müslümanların kıblesi neresidir?", "a": "Medine", "b": "Kudüs", "c": "Kabe", "d": "Mekke şehri", "dogru": "c"},
            {"konu": "Ezan", "soru": "İlk ezan okuyan kim oldu?", "a": "Hz. Ebubekir", "b": "Hz. Ali", "c": "Hz. Ömer", "d": "Hz. Bilal", "dogru": "d"},
        ],
        "veli": [
            {"soru": "Kuran-ı Kerim kaç sureden oluşur?", "a": "110", "b": "114", "c": "116", "d": "120", "dogru": "b"},
            {"soru": "Hz. Musa'nın kavmi kimlerdir?", "a": "Araplar", "b": "İbraniler (İsrailoğulları)", "c": "Romalılar", "d": "Farslar", "dogru": "b"},
            {"soru": "Zekat hangi şarta bağlıdır?", "a": "Namazı kılmak", "b": "Nisab miktarına sahip olmak", "c": "Hac yapmak", "d": "Oruç tutmak", "dogru": "b"},
            {"soru": "Hz. Peygamber hangi şehirde doğdu?", "a": "Medine", "b": "Şam", "c": "Mekke", "d": "Taif", "dogru": "c"},
        ]
    },
    "11-12": {
        "cocuk": [
            {"konu": "Kuran Tarihi", "soru": "Kuran ilk hangi surenin ayetleriyle inmeye başladı?", "a": "Fatiha", "b": "Bakara", "c": "Alak", "d": "İhlas", "dogru": "c"},
            {"konu": "Hicret", "soru": "Hicret hangi şehirden hangi şehre yapıldı?", "a": "Şam'dan Mekke'ye", "b": "Mekke'den Medine'ye", "c": "Medine'den Kudüs'e", "d": "Taif'ten Mekke'ye", "dogru": "b"},
            {"konu": "4 Büyük Kitap", "soru": "4 büyük kitap hangisinde doğru verilmiştir?", "a": "Tevrat, Zebur, İncil, Kuran", "b": "Tevrat, İncil, Suhuf, Kuran", "c": "Zebur, İncil, Suhuf, Kuran", "d": "Tevrat, Zebur, Suhuf, Kuran", "dogru": "a"},
            {"konu": "Uhud Savaşı", "soru": "Uhud Savaşı ne zaman gerçekleşti?", "a": "Hicretin 1. yılı", "b": "Hicretin 3. yılı", "c": "Hicretin 5. yılı", "d": "Hicretin 7. yılı", "dogru": "b"},
            {"konu": "Fıkıh", "soru": "Namazın farzları kaç tanedir?", "a": "6", "b": "10", "c": "12", "d": "14", "dogru": "c"},
            {"konu": "Ahlak", "soru": "Hz. Peygamberin ahlakını özetleyen kavram hangisidir?", "a": "Şecaat", "b": "Sehâvet", "c": "Üsve-i Hasene", "d": "Takva", "dogru": "c"},
            {"konu": "Tevbe", "soru": "Tevbenin kabul olması için şart değildir?", "a": "Pişmanlık duymak", "b": "Günahı bırakmak", "c": "Bir daha yapmamaya karar vermek", "d": "Ceza çekmek", "dogru": "d"},
            {"konu": "Mekke", "soru": "Mekke'nin fethi hangi yılda gerçekleşti?", "a": "Hicretin 6. yılı", "b": "Hicretin 7. yılı", "c": "Hicretin 8. yılı", "d": "Hicretin 9. yılı", "dogru": "c"},
        ],
        "veli": [
            {"soru": "Kuran'ın ilk inen ayeti hangisidir?", "a": "Bismillah", "b": "Elhamdülillah", "c": "Ikra (Oku)", "d": "La ilahe illallah", "dogru": "c"},
            {"soru": "Hicretin İslam tarihindeki önemi nedir?", "a": "İlk savaş", "b": "İslam takviminin başlangıcı", "c": "İlk vahiy", "d": "Kabe'nin inşası", "dogru": "b"},
            {"soru": "İslam'da 4 büyük halife sıralaması doğru hangisidir?", "a": "Hz. Ali, Hz. Ömer, Hz. Ebubekir, Hz. Osman", "b": "Hz. Ebubekir, Hz. Ömer, Hz. Osman, Hz. Ali", "c": "Hz. Ömer, Hz. Ebubekir, Hz. Ali, Hz. Osman", "d": "Hz. Ebubekir, Hz. Ali, Hz. Ömer, Hz. Osman", "dogru": "b"},
            {"soru": "Mekke'nin fethinde Hz. Peygamber nasıl davrandı?", "a": "Düşmanları cezalandırdı", "b": "Genel af ilan etti", "c": "Sadece Müslümanlara af çıkardı", "d": "Şehri terk etti", "dogru": "b"},
        ]
    },
    "13-14": {
        "cocuk": [
            {"konu": "Akaid", "soru": "İmanın 6 şartından biri değildir?", "a": "Allah'a iman", "b": "Meleklere iman", "c": "Peygamberlere iman", "d": "Hocalara iman", "dogru": "d"},
            {"konu": "Tefsir", "soru": "Tefsir ne demektir?", "a": "Kuran'ı ezberlemek", "b": "Kuran'ı açıklamak ve yorumlamak", "c": "Kuran'ı yazmak", "d": "Kuran'ı çevirmek", "dogru": "b"},
            {"konu": "Hadis", "soru": "Hadis ne demektir?", "a": "Kuran ayetleri", "b": "Hz. Peygamberin söz ve davranışları", "c": "Sahabe görüşleri", "d": "Fıkıh kuralları", "dogru": "b"},
            {"konu": "Fıkıh", "soru": "Fıkıh'ta 'vacip' ne demektir?", "a": "Yapılması kesin zorunlu olan", "b": "Farzdan hafif, terk edilmesi günah olan", "c": "Yapılması serbest olan", "d": "Yapılması yasak olan", "dogru": "b"},
            {"konu": "Siyer", "soru": "Hz. Peygamber kaç yaşında vefat etti?", "a": "60", "b": "63", "c": "65", "d": "70", "dogru": "b"},
            {"konu": "İslam Tarihi", "soru": "Abbasiler hangi şehri başkent yaptı?", "a": "Şam", "b": "Mekke", "c": "Bağdat", "d": "Kahire", "dogru": "c"},
            {"konu": "Tasavvuf", "soru": "Tasavvufun temel amacı nedir?", "a": "Zenginleşmek", "b": "Allah'a yakınlaşmak ve nefsi terbiye etmek", "c": "Dünyadan kaçmak", "d": "Bilgi edinmek", "dogru": "b"},
            {"konu": "Ahlak Felsefesi", "soru": "İhsan ne demektir?", "a": "Namaz kılmak", "b": "Allah'ı görüyormuş gibi ibadet etmek", "c": "Oruç tutmak", "d": "Zekat vermek", "dogru": "b"},
        ],
        "veli": [
            {"soru": "İmanın 6 şartı nelerdir? Doğru olanı seçin.", "a": "Allah, Melek, Kitap, Peygamber, Ahiret, Kader", "b": "Allah, Melek, Kitap, Peygamber, Ahiret, Cennet", "c": "Allah, Cin, Kitap, Peygamber, Ahiret, Kader", "d": "Allah, Melek, Kitap, Sahabe, Ahiret, Kader", "dogru": "a"},
            {"soru": "Hadis ilminde 'sahih hadis' ne demektir?", "a": "Kuran'da geçen ayet", "b": "Güvenilir ravilerden gelen, sağlam hadis", "c": "Yalnızca bir kişiden rivayet edilen", "d": "Sahabelerin görüşleri", "dogru": "b"},
            {"soru": "Fıkıhta 'icma' ne anlama gelir?", "a": "Bir alimin görüşü", "b": "Kuran'dan çıkarılan hüküm", "c": "İslam alimlerinin bir konuda görüş birliği", "d": "Hadislerin toplanması", "dogru": "c"},
            {"soru": "Tasavvufta 'zikir' ne demektir?", "a": "Oruç tutmak", "b": "Allah'ı anmak ve hatırlamak", "c": "Kuran okumak", "d": "Namaz kılmak", "dogru": "b"},
        ]
    }
}

# ── MODELLER ──────────────────────────────────────────────────────────────────

class ProgramCreate(BaseModel):
    program_type: str  # 'yaz' veya 'yillik'
    name: str
    start_date: str
    end_date: str

class AileCreate(BaseModel):
    program_id: str
    student_id: str | None = None
    family_name: str
    parent_phone: str
    yas_grubu: str

class CevapSubmit(BaseModel):
    family_id: str
    cocuk_dogru: bool
    veli_dogru: bool
    cocuk_hiz: bool = False
    devam: bool = False

# ── ADMIN: PROGRAM YÖNETİMİ ───────────────────────────────────────────────────

@router.get("/rota/{program_type}")
def get_rota(program_type: str):
    """Yol haritasını döndür"""
    if program_type == "yaz":
        return {"rota": YAZ_ROTA, "toplam_sehir": len(YAZ_ROTA)}
    return {"rota": YILLIK_ROTA, "toplam_sehir": len(YILLIK_ROTA)}


@router.get("/soru-bankasi/{yas_grubu}")
def get_soru_bankasi(yas_grubu: str, current: CurrentUser = Depends(require_institution)):
    """Yaş grubuna göre soru bankasını döndür"""
    if yas_grubu not in SORU_BANKASI:
        raise HTTPException(404, "Yaş grubu bulunamadı")
    return SORU_BANKASI[yas_grubu]


@router.get("/programs")
def list_programs(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("kervan_programs").select("*").eq("institution_id", current.institution_id).order("created_at", desc=True).execute()
    return res.data or []


@router.post("/programs")
def create_program(body: ProgramCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("kervan_programs").insert({
        "institution_id": current.institution_id,
        "program_type": body.program_type,
        "name": body.name,
        "start_date": body.start_date,
        "end_date": body.end_date,
    }).execute()
    return res.data[0]


@router.get("/programs/{program_id}/aileler")
def list_aileler(program_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("kervan_aileler").select("*").eq("program_id", program_id).eq("institution_id", current.institution_id).order("total_steps", desc=True).execute()
    return res.data or []


@router.post("/programs/{program_id}/aileler")
def create_aile(program_id: str, body: AileCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Program tipini al
    prog = sb.table("kervan_programs").select("program_type").eq("id", program_id).limit(1).execute()
    if not prog.data:
        raise HTTPException(404, "Program bulunamadı")
    
    res = sb.table("kervan_aileler").insert({
        "institution_id": current.institution_id,
        "program_id": program_id,
        "student_id": body.student_id,
        "family_name": body.family_name,
        "parent_phone": body.parent_phone,
        "current_city": "Konya",
        "total_steps": 0,
        "streak_days": 0,
    }).execute()
    return res.data[0]


@router.get("/programs/{program_id}/siralama")
def get_siralama(program_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("kervan_aileler").select("id,family_name,current_city,total_steps,streak_days").eq("program_id", program_id).eq("institution_id", current.institution_id).order("total_steps", desc=True).execute()
    aileler = res.data or []
    for i, a in enumerate(aileler):
        a["sira"] = i + 1
    return aileler


# ── PUBLIC: AİLE OYUN EKRANI ──────────────────────────────────────────────────

@router.get("/oyna/{family_id}")
def get_aile_durum(family_id: str):
    """Ailenin kervan durumunu döndür"""
    sb = get_supabase()
    aile = sb.table("kervan_aileler").select("*").eq("id", family_id).limit(1).execute()
    if not aile.data:
        raise HTTPException(404, "Aile bulunamadı")
    a = aile.data[0]

    # Program tipini al
    prog = sb.table("kervan_programs").select("*").eq("id", a["program_id"]).limit(1).execute()
    if not prog.data:
        raise HTTPException(404, "Program bulunamadı")
    p = prog.data[0]

    rota = YAZ_ROTA if p["program_type"] == "yaz" else YILLIK_ROTA

    # Mevcut şehir indexi
    sehir_adlari = [s["sehir"] for s in rota]
    try:
        sehir_idx = sehir_adlari.index(a["current_city"])
    except ValueError:
        sehir_idx = 0

    mevcut_sehir = rota[sehir_idx]
    sonraki_sehir = rota[sehir_idx + 1] if sehir_idx + 1 < len(rota) else None

    # Bu şehirde kaç adım atıldı
    sehir_adimlar = sb.table("kervan_sehirler").select("toplam_adim").eq("family_id", family_id).eq("sehir_adi", a["current_city"]).limit(1).execute()
    sehir_adim = sehir_adimlar.data[0]["toplam_adim"] if sehir_adimlar.data else 0

    # Bugün oynadı mı?
    bugun = date.today().isoformat()
    bugun_oyun = sb.table("kervan_adimlar").select("toplam").eq("family_id", family_id).eq("date", bugun).limit(1).execute()
    bugun_oynadı = len(bugun_oyun.data) > 0

    # Sıralama
    siralama = sb.table("kervan_aileler").select("id").eq("program_id", a["program_id"]).gt("total_steps", a["total_steps"]).execute()
    sira = len(siralama.data) + 1

    return {
        "aile": a,
        "program": p,
        "rota": rota,
        "mevcut_sehir": mevcut_sehir,
        "sonraki_sehir": sonraki_sehir,
        "sehir_idx": sehir_idx,
        "sehir_adim": sehir_adim,
        "sehir_hedef": mevcut_sehir["hedef"],
        "bugun_oynadi": bugun_oynadı,
        "sira": sira,
    }


@router.get("/oyna/{family_id}/sorular/{yas_grubu}")
def get_gunluk_sorular(family_id: str, yas_grubu: str):
    """Günlük soruları getir — önce DB'den, yoksa soru bankasından"""
    import random
    sb = get_supabase()

    aile = sb.table("kervan_aileler").select("program_id").eq("id", family_id).limit(1).execute()
    if not aile.data:
        raise HTTPException(404, "Aile bulunamadı")

    bugun = date.today().isoformat()

    # Önce hocanın girdiği soruya bak
    db_soru = sb.table("kervan_sorular").select("*").eq("program_id", aile.data[0]["program_id"]).eq("date", bugun).eq("yas_grubu", yas_grubu).limit(1).execute()

    if db_soru.data:
        s = db_soru.data[0]
        return {
            "konu": s["konu"],
            "cocuk": {"soru": s["cocuk_soru"], "a": s["cocuk_a"], "b": s["cocuk_b"], "c": s["cocuk_c"], "d": s["cocuk_d"], "dogru": s["cocuk_dogru"]},
            "veli": {"soru": s["veli_soru"], "a": s["veli_a"], "b": s["veli_b"], "c": s["veli_c"], "d": s["veli_d"], "dogru": s["veli_dogru"]},
            "kaynak": "hoca"
        }

    # Soru bankasından rastgele seç
    if yas_grubu not in SORU_BANKASI:
        yas_grubu = "7-8"
    
    banka = SORU_BANKASI[yas_grubu]
    cocuk_soru = random.choice(banka["cocuk"])
    veli_soru = random.choice(banka["veli"])

    return {
        "konu": cocuk_soru["konu"],
        "cocuk": {"soru": cocuk_soru["soru"], "a": cocuk_soru["a"], "b": cocuk_soru["b"], "c": cocuk_soru["c"], "d": cocuk_soru["d"], "dogru": cocuk_soru["dogru"]},
        "veli": {"soru": veli_soru["soru"], "a": veli_soru["a"], "b": veli_soru["b"], "c": veli_soru["c"], "d": veli_soru["d"], "dogru": veli_soru["dogru"]},
        "kaynak": "banka"
    }


@router.post("/oyna/{family_id}/cevap")
def submit_cevap(family_id: str, body: CevapSubmit):
    """Cevapları kaydet, adım hesapla, şehir geç"""
    sb = get_supabase()

    aile = sb.table("kervan_aileler").select("*").eq("id", family_id).limit(1).execute()
    if not aile.data:
        raise HTTPException(404, "Aile bulunamadı")
    a = aile.data[0]

    bugun = date.today().isoformat()

    # Bugün zaten oynadı mı?
    existing = sb.table("kervan_adimlar").select("id").eq("family_id", family_id).eq("date", bugun).limit(1).execute()
    if existing.data:
        return {"message": "Bugün zaten oynadınız", "already_played": True}

    # Puan hesapla
    devam_puan = 20 if body.devam else 0
    cocuk_puan = 20 if body.cocuk_dogru else 0
    veli_puan = 30 if body.veli_dogru else 0
    bonus = 0
    if body.cocuk_dogru and body.veli_dogru:
        bonus += 20  # İkisi de doğru bonusu
    if body.cocuk_hiz:
        bonus += 10  # Hız bonusu
    toplam = devam_puan + cocuk_puan + veli_puan + bonus

    # Adım kaydı ekle
    sb.table("kervan_adimlar").insert({
        "family_id": family_id,
        "date": bugun,
        "devam_puan": devam_puan,
        "cocuk_puan": cocuk_puan,
        "veli_puan": veli_puan,
        "bonus_puan": bonus,
        "toplam": toplam,
    }).execute()

    # Aile toplam adım güncelle
    new_total = a["total_steps"] + toplam
    new_streak = a["streak_days"] + 1

    # Şehir ilerlemesi
    prog = sb.table("kervan_programs").select("program_type").eq("id", a["program_id"]).limit(1).execute()
    rota = YAZ_ROTA if prog.data[0]["program_type"] == "yaz" else YILLIK_ROTA
    sehir_adlari = [s["sehir"] for s in rota]
    sehir_idx = sehir_adlari.index(a["current_city"]) if a["current_city"] in sehir_adlari else 0

    # Bu şehirdeki toplam adımı hesapla
    sehir_kayit = sb.table("kervan_sehirler").select("toplam_adim,id").eq("family_id", family_id).eq("sehir_adi", a["current_city"]).limit(1).execute()
    
    sehir_yeni_adim = toplam
    sehir_hedef = rota[sehir_idx]["hedef"]
    yeni_sehir = a["current_city"]
    sehre_ulasti = False

    if sehir_kayit.data:
        sehir_mevcut = sehir_kayit.data[0]["toplam_adim"]
        sehir_yeni_adim = sehir_mevcut + toplam
        sb.table("kervan_sehirler").update({"toplam_adim": sehir_yeni_adim}).eq("id", sehir_kayit.data[0]["id"]).execute()
    else:
        sb.table("kervan_sehirler").insert({
            "family_id": family_id,
            "sehir_adi": a["current_city"],
            "ulasma_tarihi": bugun,
            "toplam_adim": toplam,
        }).execute()
        sehir_yeni_adim = toplam

    # Şehir hedefine ulaşıldı mı?
    if sehir_yeni_adim >= sehir_hedef and sehir_idx + 1 < len(rota):
        yeni_sehir = rota[sehir_idx + 1]["sehir"]
        sehre_ulasti = True

    # Aile güncelle
    sb.table("kervan_aileler").update({
        "total_steps": new_total,
        "streak_days": new_streak,
        "current_city": yeni_sehir,
        "last_played": bugun,
    }).eq("id", family_id).execute()

    return {
        "already_played": False,
        "toplam_adim": toplam,
        "devam_puan": devam_puan,
        "cocuk_puan": cocuk_puan,
        "veli_puan": veli_puan,
        "bonus": bonus,
        "new_total": new_total,
        "sehir_adim": sehir_yeni_adim,
        "sehir_hedef": sehir_hedef,
        "sehre_ulasti": sehre_ulasti,
        "yeni_sehir": yeni_sehir if sehre_ulasti else None,
        "yeni_sehir_hikaye": rota[sehir_idx + 1]["hikaye"] if sehre_ulasti and sehir_idx + 1 < len(rota) else None,
    }
