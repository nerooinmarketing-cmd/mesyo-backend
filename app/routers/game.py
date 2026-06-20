"""
Kubbeler Yarışıyor — Oyun yönetimi.
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/game", tags=["game"])


# ── MODELLER ──────────────────────────────────────────────────────────────────

class QuestionCreate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str  # A, B, C, D
    time_seconds: int = 30
    hint: str | None = None
    explanation: str | None = None


class DailyGameCreate(BaseModel):
    game_date: str
    question_id: str
    open_time: str = "20:00"
    close_time: str = "23:00"
    password: str = ""


class GameAnswer(BaseModel):
    participant_phone: str
    participant_name: str | None = None
    chosen_option: str  # A, B, C, D
    time_used: int  # saniye


# ── SORULAR ──────────────────────────────────────────────────────────────────

@router.get("/questions")
def list_questions(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("game_questions")
        .select("*")
        .eq("institution_id", current.institution_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


@router.post("/questions")
def create_question(body: QuestionCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = sb.table("game_questions").insert({
        "institution_id": current.institution_id,
        "question_text": body.question_text,
        "option_a": body.option_a,
        "option_b": body.option_b,
        "option_c": body.option_c,
        "option_d": body.option_d,
        "correct_option": body.correct_option,
        "time_seconds": body.time_seconds,
        "hint": body.hint,
        "explanation": body.explanation,
    }).execute()
    return res.data[0]


@router.delete("/questions/{question_id}")
def delete_question(question_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    sb.table("game_questions").delete().eq("id", question_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}


# ── GÜNLÜK OYUNLAR ───────────────────────────────────────────────────────────

@router.get("/calendar")
def get_calendar(current: CurrentUser = Depends(require_institution)):
    """Mevcut ayın tüm günlük oyunlarını döndür."""
    sb = get_supabase()
    res = (
        sb.table("daily_games")
        .select("*, game_questions(*)")
        .eq("institution_id", current.institution_id)
        .order("game_date")
        .execute()
    )
    return res.data


@router.post("/calendar")
def create_daily_game(body: DailyGameCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Aynı gün için zaten var mı?
    existing = (
        sb.table("daily_games")
        .select("id")
        .eq("institution_id", current.institution_id)
        .eq("game_date", body.game_date)
        .limit(1)
        .execute()
    )
    data = {
        "institution_id": current.institution_id,
        "game_date": body.game_date,
        "question_ids": [body.question_id],
        "open_time": body.open_time,
        "close_time": body.close_time,
        "password": body.password or "",
        "published_by": current.id,
    }
    if existing.data:
        res = sb.table("daily_games").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        res = sb.table("daily_games").insert(data).execute()
    return res.data[0]


@router.delete("/calendar/{game_id}")
def delete_daily_game(game_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    sb.table("daily_games").delete().eq("id", game_id).eq("institution_id", current.institution_id).execute()
    return {"detail": "Silindi"}


# ── PUBLIC OYUN SAYFASI ──────────────────────────────────────────────────────

@router.get("/play/{game_id}")
def get_game_public(game_id: str):
    """Katılımcı oyun sayfası için veri. Doğru cevabı gösterme."""
    sb = get_supabase()
    res = sb.table("daily_games").select("*, game_questions(*)").eq("id", game_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oyun bulunamadı")
    game = res.data[0]

    # Soruyu bul
    q_id = game["question_ids"][0] if game["question_ids"] else None
    question = None
    if q_id:
        q_res = sb.table("game_questions").select("id,question_text,option_a,option_b,option_c,option_d,time_seconds,hint").eq("id", q_id).limit(1).execute()
        if q_res.data:
            question = q_res.data[0]  # correct_option yok — hile olmasın

    return {
        "id": game["id"],
        "game_date": game["game_date"],
        "open_time": game["open_time"],
        "close_time": game["close_time"],
        "institution_id": game["institution_id"],
        "question": question,
    }


@router.post("/play/{game_id}/answer")
def submit_answer(game_id: str, body: GameAnswer):
    """Katılımcı cevabını kaydet."""
    sb = get_supabase()

    # Oyunu bul
    game_res = sb.table("daily_games").select("*").eq("id", game_id).limit(1).execute()
    if not game_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oyun bulunamadı")
    game = game_res.data[0]

    # Soruyu ve doğru cevabı bul
    q_id = game["question_ids"][0] if game["question_ids"] else None
    if not q_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Soru bulunamadı")

    q_res = sb.table("game_questions").select("correct_option,time_seconds").eq("id", q_id).limit(1).execute()
    if not q_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Soru bulunamadı")

    question = q_res.data[0]
    correct = question["correct_option"].upper()
    chosen = body.chosen_option.upper()
    is_correct = chosen == correct

    # Puan hesapla: doğruysa 100 puan + hız bonusu
    score = 0
    if is_correct:
        max_time = question["time_seconds"]
        time_bonus = max(0, int((1 - body.time_used / max_time) * 50))
        score = 100 + time_bonus

    # Öğrenciyi telefon numarasından bul
    student_res = (
        sb.table("students")
        .select("id,first_name,last_name")
        .eq("institution_id", game["institution_id"])
        .eq("parent_phone", body.participant_phone)
        .limit(1)
        .execute()
    )
    student_id = student_res.data[0]["id"] if student_res.data else None
    student_name = f"{student_res.data[0]['first_name']} {student_res.data[0]['last_name']}" if student_res.data else body.participant_name or body.participant_phone

    # Session kaydet (upsert — aynı oyuna iki kez girilmesin)
    if student_id:
        existing = (
            sb.table("game_sessions")
            .select("id")
            .eq("daily_game_id", game_id)
            .eq("student_id", student_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return {
                "already_played": True,
                "is_correct": is_correct,
                "correct_option": correct,
                "score": score,
                "student_name": student_name,
            }

        sb.table("game_sessions").insert({
            "institution_id": game["institution_id"],
            "daily_game_id": game_id,
            "student_id": student_id,
            "child_answers": [{"questionId": q_id, "chosen": chosen, "timeUsed": body.time_used, "correct": is_correct}],
            "total_score": score,
            "score_breakdown": [{"questionId": q_id, "score": score}],
        }).execute()

    return {
        "already_played": False,
        "is_correct": is_correct,
        "correct_option": correct,
        "score": score,
        "student_name": student_name,
    }


@router.get("/play/{game_id}/leaderboard")
def get_leaderboard(game_id: str):
    """Puan tablosu — herkese açık."""
    sb = get_supabase()
    res = (
        sb.table("game_sessions")
        .select("total_score, student_id, students(first_name, last_name)")
        .eq("daily_game_id", game_id)
        .order("total_score", desc=True)
        .execute()
    )
    board = []
    for i, row in enumerate(res.data):
        student = row.get("students") or {}
        board.append({
            "rank": i + 1,
            "name": f"{student.get('first_name','')} {student.get('last_name','')}".strip() or "—",
            "score": row["total_score"],
        })
    return board
