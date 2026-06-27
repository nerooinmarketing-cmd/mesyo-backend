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
    arrival_time: str | None = None  # 'HH:MM'
    is_late: bool = False


class BulkSaveRequest(BaseModel):
    classroom_id: str
    date: str
    entries: list[AttendanceEntry]


@router.post("/bulk")
def save_bulk(body: BulkSaveRequest, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Sınıfın bu kuruma ait olduğunu doğrula
    cls_check = (
        sb.table("classrooms").select("id,lesson_start_time")
        .eq("id", body.classroom_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not cls_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz sınıf")

    lesson_start = cls_check.data[0].get("lesson_start_time")

    rows = []
    for e in body.entries:
        is_late = e.is_late
        # Eğer geliş saati ve ders başlangıç saati varsa otomatik hesapla
        if e.arrival_time and lesson_start and e.status == "present":
            is_late = e.arrival_time > lesson_start[:5]
        rows.append({
            "student_id": e.student_id,
            "classroom_id": body.classroom_id,
            "date": body.date,
            "status": e.status,
            "arrival_time": e.arrival_time,
            "is_late": is_late,
            "marked_by": current.id,
        })

    if not rows:
        return {"detail": "Kayıt yok"}

    res = sb.table("attendance_records").upsert(rows, on_conflict="student_id,date").execute()
    return {"detail": f"{len(res.data)} kayıt işlendi"}


@router.get("/dashboard-summary")
def dashboard_summary(start: str, end: str, current: CurrentUser = Depends(require_institution)):
    """Dashboard için — kurumun TÜM yoklama kayıtları, tarih aralığında, sınıf filtresi olmadan.
    Bugünkü durum ve kronik devamsızlık hesaplaması frontend'de bu veriden türetilir."""
    sb = get_supabase()
    classroom_ids_res = (
        sb.table("classrooms").select("id")
        .eq("institution_id", current.institution_id)
        .execute()
    )
    classroom_ids = [c["id"] for c in classroom_ids_res.data]
    if not classroom_ids:
        return []

    res = (
        sb.table("attendance_records").select("student_id, classroom_id, date, status")
        .in_("classroom_id", classroom_ids)
        .gte("date", start).lte("date", end)
        .execute()
    )
    return res.data


@router.get("/teacher-log")
def teacher_log(start: str, end: str, current: CurrentUser = Depends(require_institution)):
    """Bir tarih aralığında, hangi öğretmenin hangi sınıfa hangi gün yoklama girdiğini özetler.
    Her (classroom_id, date, marked_by) grubu için: kaç öğrenci işaretlendi, kaçı 'absent'.
    Sınıf/öğretmen isimlerini ayrı sorgularla çekip Python'da birleştiriyoruz —
    Supabase'in iç-içe foreign key disambiguation sentaksına bağımlı kalmamak için."""
    sb = get_supabase()
    res = (
        sb.table("attendance_records")
        .select("classroom_id, date, status, marked_by")
        .gte("date", start).lte("date", end)
        .execute()
    )
    if not res.data:
        return []

    classroom_ids = list({r["classroom_id"] for r in res.data})
    teacher_ids = list({r["marked_by"] for r in res.data if r["marked_by"]})

    classrooms_res = sb.table("classrooms").select("id, name").in_("id", classroom_ids).execute()
    classroom_names = {c["id"]: c["name"] for c in classrooms_res.data}

    teacher_names = {}
    if teacher_ids:
        teachers_res = sb.table("users").select("id, full_name").in_("id", teacher_ids).execute()
        teacher_names = {t["id"]: t["full_name"] for t in teachers_res.data}

    groups: dict[tuple, dict] = {}
    for row in res.data:
        key = (row["classroom_id"], row["date"], row["marked_by"])
        if key not in groups:
            groups[key] = {
                "classroom_id": row["classroom_id"],
                "date": row["date"],
                "marked_by": row["marked_by"],
                "classroom_name": classroom_names.get(row["classroom_id"], "—"),
                "teacher_name": teacher_names.get(row["marked_by"], "—"),
                "count": 0,
                "absent": 0,
            }
        groups[key]["count"] += 1
        if row["status"] == "absent":
            groups[key]["absent"] += 1

    return sorted(groups.values(), key=lambda g: g["date"], reverse=True)


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


@router.get("/late-report")
def late_report(classroom_id: str, start: str, end: str, current: CurrentUser = Depends(require_institution)):
    """Geç gelen öğrenciler raporu"""
    sb = get_supabase()

    # Sınıf kontrolü
    cls_check = sb.table("classrooms").select("id,name,lesson_start_time,lesson_end_time").eq("id", classroom_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not cls_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz sınıf")
    cls = cls_check.data[0]

    # Geç gelen kayıtlar
    res = sb.table("attendance_records").select(
        "student_id, date, arrival_time, is_late, status"
    ).eq("classroom_id", classroom_id).eq("is_late", True).gte("date", start).lte("date", end).execute()

    late_records = res.data or []

    # Öğrenci bilgilerini çek
    student_ids = list({r["student_id"] for r in late_records})
    students_map = {}
    if student_ids:
        sts = sb.table("students").select("id,first_name,last_name,parent_name,parent_phone").in_("id", student_ids).execute()
        students_map = {s["id"]: s for s in (sts.data or [])}

    # Öğrenci bazında grupla
    grouped: dict = {}
    for r in late_records:
        sid = r["student_id"]
        if sid not in grouped:
            s = students_map.get(sid, {})
            grouped[sid] = {
                "student_id": sid,
                "full_name": f"{s.get('first_name','')} {s.get('last_name','')}".strip(),
                "parent_name": s.get("parent_name", ""),
                "parent_phone": s.get("parent_phone", ""),
                "late_count": 0,
                "records": [],
            }
        grouped[sid]["late_count"] += 1
        grouped[sid]["records"].append({
            "date": r["date"],
            "arrival_time": r["arrival_time"],
        })

    result = sorted(grouped.values(), key=lambda x: x["late_count"], reverse=True)

    return {
        "classroom": cls,
        "period": {"start": start, "end": end},
        "total_late_records": len(late_records),
        "students": result,
    }


@router.patch("/classrooms/{classroom_id}/lesson-time")
def update_lesson_time(classroom_id: str, body: dict, current: CurrentUser = Depends(require_institution)):
    """Sınıf ders saatini güncelle"""
    sb = get_supabase()
    sb.table("classrooms").update({
        "lesson_start_time": body.get("lesson_start_time"),
        "lesson_end_time": body.get("lesson_end_time"),
    }).eq("id", classroom_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Ders saati güncellendi"}


@router.get("/late-report/student/{student_id}")
def late_report_student(student_id: str, current: CurrentUser = Depends(require_institution)):
    """Öğrenci bazlı geç gelme raporu"""
    sb = get_supabase()

    # Öğrenci kontrolü
    st = sb.table("students").select("id,first_name,last_name,parent_name,parent_phone,classroom_id").eq("id", student_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not st.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Öğrenci bulunamadı")
    student = st.data[0]

    # Geç gelme kayıtları
    res = sb.table("attendance_records").select("date,arrival_time,is_late,status").eq("student_id", student_id).eq("is_late", True).order("date", desc=True).execute()
    late_records = res.data or []

    # Tüm yoklama sayısı
    all_res = sb.table("attendance_records").select("status").eq("student_id", student_id).execute()
    all_records = all_res.data or []
    total_present = sum(1 for r in all_records if r["status"] == "present")

    return {
        "student": student,
        "late_count": len(late_records),
        "total_present": total_present,
        "late_rate": round(len(late_records) / total_present * 100, 1) if total_present else 0,
        "records": late_records,
    }


@router.get("/late-report/all")
def late_report_all(start: str, end: str, current: CurrentUser = Depends(require_institution)):
    """Tüm kurum öğrencileri geç gelme raporu — öğrenci bazlı"""
    sb = get_supabase()

    # Kurumun tüm sınıfları
    cls_res = sb.table("classrooms").select("id").eq("institution_id", current.institution_id).execute()
    cls_ids = [c["id"] for c in (cls_res.data or [])]
    if not cls_ids:
        return {"students": [], "total": 0}

    # Geç gelme kayıtları
    res = sb.table("attendance_records").select(
        "student_id, date, arrival_time, classroom_id"
    ).in_("classroom_id", cls_ids).eq("is_late", True).gte("date", start).lte("date", end).execute()

    late_records = res.data or []
    student_ids = list({r["student_id"] for r in late_records})

    students_map = {}
    if student_ids:
        sts = sb.table("students").select("id,first_name,last_name,parent_name,parent_phone").in_("id", student_ids).execute()
        students_map = {s["id"]: s for s in (sts.data or [])}

    grouped: dict = {}
    for r in late_records:
        sid = r["student_id"]
        if sid not in grouped:
            s = students_map.get(sid, {})
            grouped[sid] = {
                "student_id": sid,
                "full_name": f"{s.get('first_name','')} {s.get('last_name','')}".strip(),
                "parent_name": s.get("parent_name", ""),
                "parent_phone": s.get("parent_phone", ""),
                "late_count": 0,
                "records": [],
            }
        grouped[sid]["late_count"] += 1
        grouped[sid]["records"].append({"date": r["date"], "arrival_time": r["arrival_time"]})

    result = sorted(grouped.values(), key=lambda x: x["late_count"], reverse=True)
    return {"students": result, "total": len(late_records)}
