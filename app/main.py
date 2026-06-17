"""
Mesyo Soft Backend — FastAPI + Supabase
Çalıştırma: uvicorn app.main:app --reload --port 8200
Frontend'in .env'indeki VITE_API_URL bu sunucunun /api yoluna işaret etmeli.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, students, classrooms, teachers, seasons, attendance, superadmin, institution, public, assignments, skills, applications, payments, modules, users

app = FastAPI(title="Mesyo Soft API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tüm router'lar /api prefix'i altında — frontend lib/api.ts'teki API_URL
# zaten ".../api" ile bittiği için burada tekrar prefix eklemiyoruz, router'lar
# kendi prefix'lerini (örn. /students) doğrudan app'e bağlıyor ve app /api altında mount ediliyor.
api_app = FastAPI()
api_app.include_router(auth.router)
api_app.include_router(students.router)
api_app.include_router(classrooms.router)
api_app.include_router(teachers.router)
api_app.include_router(seasons.router)
api_app.include_router(attendance.router)
api_app.include_router(superadmin.router)
api_app.include_router(institution.router)
api_app.include_router(public.router)
api_app.include_router(assignments.router)
api_app.include_router(skills.router)
api_app.include_router(applications.router)
api_app.include_router(payments.router)
api_app.include_router(modules.router)
api_app.include_router(users.router)

app.mount("/api", api_app)


@app.get("/health")
def health():
    """Hetzner'de servisin ayakta olup olmadığını kontrol etmek için (örn. systemd, uptime monitor)."""
    return {"status": "ok"}
