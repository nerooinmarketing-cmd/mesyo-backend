"""
Performans/beceri takibi.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillLevelUpdate(BaseModel):
    student_id: str
    skill_id: str
    level: str


class BulkLevelUpdate(BaseModel):
    updates: list[SkillLevelUpdate]


@router.get("")
def list_skills(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("skills")
        .select("*")
        .or_(f"institution_id.is.null,institution_id.eq.{current.institution_id}")
        .order("sort_order")
        .execute()
    )
    return res.data


@router.get("/classroom/{classroom_id}")
def classroom_skill_levels(classroom_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    cls_check = (
        sb.table("classrooms").select("id")
        .eq("id", classroom_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not cls_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Gecersiz sinif")

    students_res = (
        sb.table("students").select("id")
        .eq("classroom_id", classroom_id).eq("institution_id", current.institution_id)
        .execute()
    )
    student_ids = [s["id"] for s in students_res.data]
    if not student_ids:
        return {}

    levels_res = (
        sb.table("student_skills").select("student_id, skill_id, level")
        .in_("student_id", student_ids)
        .execute()
    )

    result: dict[str, dict[str, str]] = {}
    for row in levels_res.data:
        result.setdefault(row["student_id"], {})[row["skill_id"]] = row["level"]
    return result


@router.post("/levels")
def update_levels(body: BulkLevelUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    if not body.updates:
        return {"detail": "Guncellenecek kayit yok"}

    student_ids = list({u.student_id for u in body.updates})
    check = (
        sb.table("students").select("id")
        .in_("id", student_ids).eq("institution_id", current.institution_id)
        .execute()
    )
    valid_ids = {r["id"] for r in check.data}
    invalid = [sid for sid in student_ids if sid not in valid_ids]
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bazi ogrenciler bu kuruma ait degil")

    rows = [
        {
            "student_id": u.student_id,
            "skill_id": u.skill_id,
            "level": u.level,
            "updated_by": current.id,
        }
        for u in body.updates
    ]
    sb.table("student_skills").upsert(rows, on_conflict="student_id,skill_id").execute()
    return {"detail": f"{len(rows)} kayit guncellendi"}
