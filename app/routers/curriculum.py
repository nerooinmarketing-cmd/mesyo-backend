from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser
from datetime import date

router = APIRouter(prefix="/curriculum", tags=["curriculum"])

# ── MODELLER ──────────────────────────────────────────────────────────────────

class TopicCreate(BaseModel):
    classroom_id: str | None = None
    title: str
    description: str | None = None
    period_type: str  # daily, weekly, monthly
    order_index: int = 0

class TopicUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    period_type: str | None = None
    order_index: int | None = None

class AssignmentCreate(BaseModel):
    topic_id: str | None = None
    classroom_id: str
    title: str
    description: str | None = None
    due_date: str | None = None
    student_ids: list[str] | None = None  # None = tüm sınıf

class CompletionUpdate(BaseModel):
    student_id: str
    assignment_id: str
    is_done: bool

class ReportCreate(BaseModel):
    student_id: str
    classroom_id: str
    week_start: str
    week_end: str
    teacher_comment: str | None = None
    focus_areas: str | None = None

# ── MÜFREDAT KONULARI ─────────────────────────────────────────────────────────

@router.get("/topics")
def list_topics(classroom_id: str | None = None, period_type: str | None = None,
                current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    q = sb.table("curriculum_topics").select("*").eq("institution_id", current.institution_id)
    if classroom_id:
        q = q.eq("classroom_id", classroom_id)
    if period_type:
        q = q.eq("period_type", period_type)
    res = q.order("order_index").order("created_at").execute()
    return res.data or []


@router.post("/topics")
def create_topic(body: TopicCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("curriculum_topics").insert({
        "institution_id": current.institution_id,
        "classroom_id": body.classroom_id,
        "title": body.title,
        "description": body.description,
        "period_type": body.period_type,
        "order_index": body.order_index,
        "created_by": current.id,
    }).execute()
    return res.data[0]


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: str, body: TopicUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    res = sb.table("curriculum_topics").update(data).eq("id", topic_id).eq("institution_id", current.institution_id).execute()
    return res.data[0] if res.data else {}


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    sb.table("curriculum_topics").delete().eq("id", topic_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}

# ── MÜFREDATTAN ÖDEV ─────────────────────────────────────────────────────────

@router.get("/assignments")
def list_assignments(classroom_id: str | None = None, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    q = sb.table("curriculum_assignments").select("*, curriculum_topics(title, period_type)").eq("institution_id", current.institution_id)
    if classroom_id:
        q = q.eq("classroom_id", classroom_id)
    res = q.order("assigned_date", desc=True).execute()
    return res.data or []


@router.post("/assignments")
def create_assignment(body: AssignmentCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Sınıf kontrolü
    cls = sb.table("classrooms").select("id").eq("id", body.classroom_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not cls.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz sınıf")

    asgn = sb.table("curriculum_assignments").insert({
        "institution_id": current.institution_id,
        "topic_id": body.topic_id,
        "classroom_id": body.classroom_id,
        "title": body.title,
        "description": body.description,
        "due_date": body.due_date,
        "assigned_date": date.today().isoformat(),
        "created_by": current.id,
    }).execute()
    assignment = asgn.data[0]

    # Öğrenci tamamlama kayıtları oluştur
    if body.student_ids:
        student_ids = body.student_ids
    else:
        students = sb.table("students").select("id").eq("classroom_id", body.classroom_id).eq("institution_id", current.institution_id).eq("status", "approved").execute()
        student_ids = [s["id"] for s in (students.data or [])]

    if student_ids:
        completions = [{"assignment_id": assignment["id"], "student_id": sid, "is_done": False} for sid in student_ids]
        sb.table("assignment_completions").insert(completions).execute()

    return assignment


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    sb.table("assignment_completions").delete().eq("assignment_id", assignment_id).execute()
    sb.table("curriculum_assignments").delete().eq("id", assignment_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}


@router.get("/assignments/{assignment_id}/completions")
def get_completions(assignment_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Önce ödevin bu kuruma ait olduğunu doğrula
    asgn = sb.table("curriculum_assignments").select("id,classroom_id").eq("id", assignment_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not asgn.data:
        raise HTTPException(404, "Ödev bulunamadı")

    res = sb.table("assignment_completions").select("*, students(first_name, last_name, full_name, parent_name, parent_phone)").eq("assignment_id", assignment_id).execute()
    return res.data or []


@router.patch("/completions")
def update_completion(body: CompletionUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = {"is_done": body.is_done}
    if body.is_done:
        data["done_at"] = date.today().isoformat()
    else:
        data["done_at"] = None

    existing = sb.table("assignment_completions").select("id").eq("assignment_id", body.assignment_id).eq("student_id", body.student_id).limit(1).execute()
    if existing.data:
        sb.table("assignment_completions").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        sb.table("assignment_completions").insert({"assignment_id": body.assignment_id, "student_id": body.student_id, **data}).execute()
    return {"detail": "Güncellendi"}

# ── HAFTALIK KARNE ────────────────────────────────────────────────────────────

@router.get("/reports")
def list_reports(classroom_id: str | None = None, week_start: str | None = None,
                 current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    q = sb.table("student_reports").select("*, students(first_name, last_name, full_name, parent_name, parent_phone)").eq("institution_id", current.institution_id)
    if classroom_id:
        q = q.eq("classroom_id", classroom_id)
    if week_start:
        q = q.eq("week_start", week_start)
    res = q.order("week_start", desc=True).execute()
    return res.data or []


@router.post("/reports")
def create_report(body: ReportCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("student_reports").upsert({
        "institution_id": current.institution_id,
        "student_id": body.student_id,
        "classroom_id": body.classroom_id,
        "week_start": body.week_start,
        "week_end": body.week_end,
        "teacher_comment": body.teacher_comment,
        "focus_areas": body.focus_areas,
        "created_by": current.id,
    }, on_conflict="student_id,week_start").execute()
    return res.data[0]


@router.get("/reports/student/{student_id}")
def get_student_reports(student_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Öğrencinin bu kuruma ait olduğunu doğrula
    st = sb.table("students").select("id").eq("id", student_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not st.data:
        raise HTTPException(404, "Öğrenci bulunamadı")
    res = sb.table("student_reports").select("*").eq("student_id", student_id).order("week_start", desc=True).execute()
    return res.data or []


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    sb.table("student_reports").delete().eq("id", report_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}
