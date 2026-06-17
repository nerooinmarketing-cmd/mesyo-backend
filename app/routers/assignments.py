"""
Ödev (assignment) takibi. WhatsApp mesajının kendisini bu backend göndermez —
frontend doğrudan wa.me linki açar (waLink). Burada sadece "kim ne zaman hangi
ödevi hangi öğrencilere gönderdi" kaydı tutulur, geçmiş sekmesi için.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/assignments", tags=["assignments"])


class AssignmentCreate(BaseModel):
    classroom_id: str
    title: str
    description: str
    due_date: str | None = None
    student_ids: list[str]  # gönderim yapılan öğrenciler — assignment_recipients'a yazılır


@router.get("")
def list_assignments(classroom_id: str | None = None, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    q = sb.table("assignments").select("*, assignment_recipients(student_id)").eq(
        "institution_id", current.institution_id
    )
    if classroom_id:
        q = q.eq("classroom_id", classroom_id)
    res = q.order("created_at", desc=True).execute()

    # sentCount frontend'in beklediği alan adı (camelCase) — assignment_recipients sayısından çıkarılır
    result = []
    for a in res.data:
        recipients = a.pop("assignment_recipients", [])
        a["sent_count"] = len(recipients)
        result.append(a)
    return result


@router.post("")
def create_assignment(body: AssignmentCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Sınıfın bu kuruma ait olduğunu doğrula
    cls_check = (
        sb.table("classrooms").select("id")
        .eq("id", body.classroom_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not cls_check.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz sınıf")

    assignment_data = {
        "institution_id": current.institution_id,
        "classroom_id": body.classroom_id,
        "title": body.title,
        "description": body.description,
        "due_date": body.due_date,
        "created_by": current.id,
    }
    res = sb.table("assignments").insert(assignment_data).execute()
    assignment = res.data[0]

    if body.student_ids:
        recipients = [{"assignment_id": assignment["id"], "student_id": sid} for sid in body.student_ids]
        sb.table("assignment_recipients").upsert(recipients, on_conflict="assignment_id,student_id").execute()

    assignment["sent_count"] = len(body.student_ids)
    return assignment


@router.delete("/{assignment_id}")
def delete_assignment(assignment_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("assignments").delete()
        .eq("id", assignment_id).eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödev bulunamadı")
    return {"detail": "Silindi"}
