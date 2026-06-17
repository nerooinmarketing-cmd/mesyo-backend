"""
Mesyo Soft Backend - FastAPI + Supabase
Calistirma: uvicorn app.main:app --reload --port 8200
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, students, classrooms, teachers, seasons, attendance, superadmin, institution, public, assignments, skills

app = FastAPI(title="Mesyo Soft API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

app.mount("/api", api_app)


@app.get("/health")
def health():
    return {"status": "ok"}
