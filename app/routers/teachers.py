"""
Öğretmen yönetimi (institution_admin tarafından) + öğretmenin kendi verilerine
erişimi (myClassrooms, myStudents).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.security import hash_password
from app.core.deps import require_institution, get_current_user, CurrentUser

router = APIRouter(prefix="/teachers", tags=["teachers"])


class TeacherCreate(BaseModel):
    full_name: str
    phone: str
    password: str
    see_all: bool = False
    class_id: str | None = None


class TeacherUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    see_all_classrooms: bool | None = None
    class_id: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str


def _teacher_row_to_response(row: dict, classroom_name: str | None = None) -> dict:
    return {
        "id": row["id"],
        "institution_id": row["institution_id"],
        "full_name": row["full_name"],
        "phone": row["phone"],
        "class_id": row.get("_class_id"),
        "class_name": classroom_name,
        "is_active": row["is_active"],
        "see_all": row.get("see_all_classrooms", False),
        "wa_connected": row.get("wa_connected", False),
    }


@router.get("")
def list_teachers(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    teachers_res = (
        sb.table("users")
        .select("*")
        .eq("institution_id", current.institution_id)
        .eq("role", "teacher")
        .order("full_name")
        .execute()
    )
    classrooms_res = (
        sb.table("classrooms")
        .select("id, name, teacher_id")
        .eq("institution_id", current.institution_id)
        .execute()
    )
    classroom_by_teacher = {c["teacher_id"]: c for c in classrooms_res.data if c.get("teacher_id")}

    result = []
    for t in teachers_res.data:
        cls = classroom_by_teacher.get(t["id"])
        t["_class_id"] = cls["id"] if cls else None
        result.append(_teacher_row_to_response(t, cls["name"] if cls else None))
    return result


@router.post("")
def create_teacher(body: TeacherCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    existing = (
        sb.table("users").select("id")
        .eq("institution_id", current.institution_id).eq("phone", body.phone)
        .limit(1).execute()
    )
    if existing.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu telefon numarası ile zaten bir kullanıcı var")

    data = {
        "institution_id": current.institution_id,
        "full_name": body.full_name,
        "phone": body.phone,
        "password_hash": hash_password(body.password),
        "role": "teacher",
        "see_all_classrooms": body.see_all,
        "must_change_password": True,
    }
    res = sb.table("users").insert(data).execute()
    teacher = res.data[0]

    if body.class_id:
        sb.table("classrooms").update({"teacher_id": teacher["id"]}).eq("id", body.class_id).eq(
            "institution_id", current.institution_id
        ).execute()

    return _teacher_row_to_response({**teacher, "_class_id": body.class_id})


@router.patch("/{teacher_id}")
def update_teacher(teacher_id: str, body: TeacherUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude={"class_id"}, exclude_none=True)

    if data:
        res = (
            sb.table("users").update(data)
            .eq("id", teacher_id).eq("institution_id", current.institution_id).eq("role", "teacher")
            .execute()
        )
        if not res.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğretmen bulunamadı")

    if body.class_id is not None:
        # Önce bu öğretmenin eski sınıf atamasını kaldır, sonra yeniyi ata
        sb.table("classrooms").update({"teacher_id": None}).eq("teacher_id", teacher_id).eq(
            "institution_id", current.institution_id
        ).execute()
        if body.class_id:
            sb.table("classrooms").update({"teacher_id": teacher_id}).eq("id", body.class_id).eq(
                "institution_id", current.institution_id
            ).execute()

    final = sb.table("users").select("*").eq("id", teacher_id).limit(1).execute()
    if not final.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğretmen bulunamadı")
    return _teacher_row_to_response({**final.data[0], "_class_id": body.class_id})


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("users").delete()
        .eq("id", teacher_id).eq("institution_id", current.institution_id).eq("role", "teacher")
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğretmen bulunamadı")
    return {"detail": "Silindi"}


@router.post("/{teacher_id}/reset-password")
def reset_password(teacher_id: str, body: ResetPasswordRequest, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("users").update({
            "password_hash": hash_password(body.new_password),
            "must_change_password": True,
        })
        .eq("id", teacher_id).eq("institution_id", current.institution_id).eq("role", "teacher")
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğretmen bulunamadı")
    return {"detail": "Şifre sıfırlandı"}


@router.get("/me/classrooms")
def my_classrooms(current: CurrentUser = Depends(get_current_user)):
    if current.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sadece öğretmenler için")
    sb = get_supabase()

    user_res = sb.table("users").select("see_all_classrooms").eq("id", current.id).limit(1).execute()
    see_all = user_res.data[0]["see_all_classrooms"] if user_res.data else False

    q = sb.table("classrooms").select("*").eq("institution_id", current.institution_id)
    if not see_all:
        q = q.eq("teacher_id", current.id)
    res = q.execute()
    return res.data


@router.get("/me/students")
def my_students(current: CurrentUser = Depends(get_current_user)):
    if current.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sadece öğretmenler için")
    sb = get_supabase()

    user_res = sb.table("users").select("see_all_classrooms").eq("id", current.id).limit(1).execute()
    see_all = user_res.data[0]["see_all_classrooms"] if user_res.data else False

    if see_all:
        res = (
            sb.table("students").select("*")
            .eq("institution_id", current.institution_id).eq("status", "approved")
            .execute()
        )
        return res.data

    cls_res = (
        sb.table("classrooms").select("id")
        .eq("institution_id", current.institution_id).eq("teacher_id", current.id)
        .execute()
    )
    classroom_ids = [c["id"] for c in cls_res.data]
    if not classroom_ids:
        return []

    res = (
        sb.table("students").select("*")
        .eq("institution_id", current.institution_id).eq("status", "approved")
        .in_("classroom_id", classroom_ids)
        .execute()
    )
    return res.data
