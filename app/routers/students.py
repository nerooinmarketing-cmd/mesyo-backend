"""
Öğrenci endpoint'leri. Frontend lib/api.ts'teki studentsApi ile bire bir eşleşir.

KURUM İZOLASYONU: Her sorguya .eq("institution_id", current.institution_id)
ekliyoruz — bu, bir kurumun başka bir kurumun öğrencisini görmesini/değiştirmesini
engelleyen tek katman (RLS'i service_role ile bypass ettiğimiz için).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import get_current_user, require_institution, CurrentUser

router = APIRouter(prefix="/students", tags=["students"])


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    birth_date: str
    gender: str
    tc_no: str | None = None
    city: str | None = "Konya"
    district: str | None = "Meram"
    mahalle: str | None = None
    sokak: str | None = None
    address: str | None = None
    parent_first_name: str
    parent_last_name: str
    parent_phone: str
    parent_phone2: str | None = None
    notes: str | None = None
    classroom_id: str | None = None
    season_id: str | None = None


class StudentUpdate(BaseModel):
    """Tüm alanlar opsiyonel — sadece gönderilenler güncellenir (PATCH semantiği)."""
    first_name: str | None = None
    last_name: str | None = None
    birth_date: str | None = None
    gender: str | None = None
    tc_no: str | None = None
    city: str | None = None
    district: str | None = None
    mahalle: str | None = None
    sokak: str | None = None
    address: str | None = None
    parent_first_name: str | None = None
    parent_last_name: str | None = None
    parent_phone: str | None = None
    parent_phone2: str | None = None
    notes: str | None = None
    classroom_id: str | None = None


class RejectRequest(BaseModel):
    reason: str | None = None


class AssignClassroomRequest(BaseModel):
    classroom_id: str


@router.get("")
def list_students(
    season_id: str | None = None,
    classroom_id: str | None = None,
    status_filter: str | None = None,
    gender: str | None = None,
    current: CurrentUser = Depends(require_institution),
):
    sb = get_supabase()
    q = sb.table("students").select("*").eq("institution_id", current.institution_id)

    if season_id:
        q = q.eq("season_id", season_id)
    if classroom_id:
        q = q.eq("classroom_id", classroom_id)
    if status_filter:
        q = q.eq("status", status_filter)
    if gender:
        q = q.eq("gender", gender)

    res = q.order("created_at", desc=True).execute()
    return res.data


@router.get("/{student_id}")
def get_student(student_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("students")
        .select("*")
        .eq("id", student_id)
        .eq("institution_id", current.institution_id)  # başka kurumun öğrencisine erişimi engeller
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    return res.data[0]


@router.post("")
def create_student(body: StudentCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    data["institution_id"] = current.institution_id
    data.setdefault("status", "approved")
    data["registration_source"] = "manual"
    data["kvkk_consent"] = True

    res = sb.table("students").insert(data).execute()
    return res.data[0]


class BulkStudentItem(BaseModel):
    first_name: str
    last_name: str
    full_name: str | None = None
    birth_date: str | None = None
    gender: str = "kiz"
    age: int | None = None
    tc_no: str | None = None
    address: str | None = None
    mahalle: str | None = None
    parent_name: str
    parent_first_name: str | None = None
    parent_last_name: str | None = None
    parent_address: str | None = None
    parent_phone: str
    registration_date: str | None = None
    classroom_id: str | None = None
    season_id: str | None = None


class BulkStudentCreate(BaseModel):
    students: list[BulkStudentItem]
    season_id: str | None = None


@router.post("/bulk-import")
def bulk_import_students(body: BulkStudentCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    if not body.students:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Öğrenci listesi boş")
    if len(body.students) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "En fazla 200 öğrenci yüklenebilir")

    # Aktif sezonu bul
    season_id = body.season_id
    if not season_id:
        active = sb.table("seasons").select("id").eq("institution_id", current.institution_id).eq("is_active", True).limit(1).execute()
        if active.data:
            season_id = active.data[0]["id"]

    rows = []
    errors = []
    for i, s in enumerate(body.students):
        if not s.first_name or not s.last_name or not s.parent_name or not s.parent_phone:
            errors.append(f"Satır {i+2}: Ad, soyad, veli adı ve telefon zorunlu")
            continue
        if s.gender not in ("kiz", "erkek"):
            errors.append(f"Satır {i+2}: Cinsiyet 'kiz' veya 'erkek' olmalı")
            continue

        row = {
            "institution_id": current.institution_id,
            "first_name": s.first_name.strip(),
            "last_name": s.last_name.strip(),
            "full_name": s.full_name or f"{s.first_name.strip()} {s.last_name.strip()}",
            "gender": s.gender,
            "parent_name": s.parent_name.strip(),
            "parent_phone": s.parent_phone.strip(),
            "status": "approved",
            "registration_source": "excel",
            "kvkk_consent": True,
            "registration_date": s.registration_date or __import__("datetime").date.today().isoformat(),
        }
        if s.birth_date: row["birth_date"] = s.birth_date
        if s.tc_no: row["tc_no"] = s.tc_no
        if s.age: row["age"] = s.age
        if s.address: row["address"] = s.address
        if s.mahalle: row["mahalle"] = s.mahalle
        if s.parent_first_name: row["parent_first_name"] = s.parent_first_name
        if s.parent_last_name: row["parent_last_name"] = s.parent_last_name
        if s.parent_address: row["parent_address"] = s.parent_address
        if s.registration_date: row["registration_date"] = s.registration_date
        if s.classroom_id: row["classroom_id"] = s.classroom_id
        if season_id: row["season_id"] = season_id
        rows.append(row)

    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"errors": errors})

    res = sb.table("students").insert(rows).execute()
    return {"detail": f"{len(res.data)} öğrenci eklendi", "count": len(res.data)}


@router.patch("/{student_id}")
def update_student(student_id: str, body: StudentUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")

    res = (
        sb.table("students")
        .update(data)
        .eq("id", student_id)
        .eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    return res.data[0]


@router.delete("/{student_id}")
def delete_student(student_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("students")
        .delete()
        .eq("id", student_id)
        .eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    return {"detail": "Silindi"}


@router.post("/{student_id}/approve")
def approve_student(student_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("students")
        .update({"status": "approved"})
        .eq("id", student_id)
        .eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    return res.data[0]


@router.post("/{student_id}/reject")
def reject_student(student_id: str, body: RejectRequest, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    update_data = {"status": "rejected"}
    if body.reason:
        update_data["notes"] = body.reason
    res = (
        sb.table("students")
        .update(update_data)
        .eq("id", student_id)
        .eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    return res.data[0]


@router.post("/{student_id}/classroom")
def assign_classroom(student_id: str, body: AssignClassroomRequest, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Sınıfın da aynı kuruma ait olduğunu doğrula — başka kurumun sınıfına atama yapılmasın
    cls_check = (
        sb.table("classrooms")
        .select("id")
        .eq("id", body.classroom_id)
        .eq("institution_id", current.institution_id)
        .limit(1)
        .execute()
    )
    if not cls_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz sınıf")

    res = (
        sb.table("students")
        .update({"classroom_id": body.classroom_id})
        .eq("id", student_id)
        .eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    return res.data[0]
