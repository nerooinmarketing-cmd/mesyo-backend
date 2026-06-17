"""
Yoklama. attendance_records tablosunda (student_id, date) unique olduğu için
upsert kullanıyoruz — aynı gün tekrar yoklama alınırsa üzerine yazar, hata vermez.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/attendance", tags=["attendance"])


class AttendanceEntry(BaseModel):
    student_id: str
    status: str  # 'present' | 'absent' | 'late' | 'excused'


class BulkSaveRequest(BaseModel):
    classroom_id: str
    date: str
    entries: list[AttendanceEntry]


@router.post("/bulk")
def save_bulk(body: BulkSaveRequest, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Sınıfın bu kuruma ait olduğunu doğrula
    cls_check = (
        sb.table("classrooms").select("id")
        .eq("id", body.classroom_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not cls_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz sınıf")

    rows = [
        {
            "student_id": e.student_id,
            "classroom_id": body.classroom_id,
            "date": body.date,
            "status": e.status,
            "marked_by": current.id,
        }
        for e in body.entries
    ]
    if not rows:
        return {"detail": "Kayıt yok"}

    # upsert: (student_id, date) unique constraint'i sayesinde aynı güne tekrar
    # yoklama alınırsa üzerine yazar.
    res = sb.table("attendance_records").upsert(rows, on_conflict="student_id,date").execute()
    return {"detail": f"{len(res.data)} kayıt işlendi"}


@router.get("")
def get_by_date(classroom_id: str, date: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("attendance_records")
        .select("*")
        .eq("classroom_id", classroom_id)
        .eq("date", date)
        .execute()
    )
    return res.data


@router.get("/report")
def get_report(classroom_id: str, start: str, end: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("attendance_records")
        .select("*, students(first_name, last_name, parent_first_name, parent_last_name, parent_phone)")
        .eq("classroom_id", classroom_id)
        .gte("date", start)
        .lte("date", end)
        .order("date")
        .execute()
    )
    return res.data


@router.get("/student/{student_id}/summary")
def student_summary(student_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Öğrencinin bu kuruma ait olduğunu doğrula
    student_check = (
        sb.table("students").select("id")
        .eq("id", student_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not student_check.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")

    res = sb.table("attendance_records").select("status, date").eq("student_id", student_id).execute()
    records = res.data
    total = len(records)
    present = sum(1 for r in records if r["status"] == "present")
    absent = sum(1 for r in records if r["status"] == "absent")

    return {
        "total": total,
        "present": present,
        "absent": absent,
        "rate": round(present / total * 100, 1) if total else 0,
        "records": records,
    }
