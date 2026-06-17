from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/classrooms", tags=["classrooms"])


class ClassroomCreate(BaseModel):
    name: str
    age_group: str | None = None
    capacity: int = 30
    season_id: str
    teacher_id: str | None = None


class ClassroomUpdate(BaseModel):
    name: str | None = None
    age_group: str | None = None
    capacity: int | None = None
    teacher_id: str | None = None
    is_active: bool | None = None


class AssignTeacherRequest(BaseModel):
    teacher_id: str


@router.get("")
def list_classrooms(season_id: str | None = None, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    q = sb.table("classrooms").select("*").eq("institution_id", current.institution_id)
    if season_id:
        q = q.eq("season_id", season_id)
    res = q.order("name").execute()
    return res.data


@router.post("")
def create_classroom(body: ClassroomCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    data["institution_id"] = current.institution_id
    res = sb.table("classrooms").insert(data).execute()
    return res.data[0]


@router.patch("/{classroom_id}")
def update_classroom(classroom_id: str, body: ClassroomUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")
    res = (
        sb.table("classrooms").update(data)
        .eq("id", classroom_id).eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sınıf bulunamadı")
    return res.data[0]


@router.delete("/{classroom_id}")
def delete_classroom(classroom_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("classrooms").delete()
        .eq("id", classroom_id).eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sınıf bulunamadı")
    return {"detail": "Silindi"}


@router.post("/{classroom_id}/teacher")
def assign_teacher(classroom_id: str, body: AssignTeacherRequest, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    teacher_check = (
        sb.table("users").select("id")
        .eq("id", body.teacher_id).eq("institution_id", current.institution_id).eq("role", "teacher")
        .limit(1).execute()
    )
    if not teacher_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz öğretmen")

    res = (
        sb.table("classrooms").update({"teacher_id": body.teacher_id})
        .eq("id", classroom_id).eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sınıf bulunamadı")
    return res.data[0]
