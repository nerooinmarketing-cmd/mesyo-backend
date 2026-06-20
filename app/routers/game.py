"""
Kubbeler Yarışıyor — Oyun yönetimi.
Akış: Hoca şifre+6 soru girer → veli linke tıklar → şifreyi girer →
      çocuk 3 soru cevaplar → veli 3 soru cevaplar → puan tablosu
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/game", tags=["game"])


# ── MODELLER ──────────────────────────────────────────────────────────────────

class GameQuestion(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str   # A, B, C, D
    time_seconds: int = 30
    player_type: str = "child"  # child | parent


class DailyGameCreate(BaseModel):
    game_date: str
    password: str
    classroom_id: str | None = None
    open_time: str = "20:00"
    close_time: str = "23:00"
    questions: list[GameQuestion]  # ilk 3 child, son 3 parent


class AnswerSubmit(BaseModel):
    game_id: str
    parent_phone: str
    child_answers: list[dict]   # [{question_index, chosen, time_used}]
    parent_answers: list[dict]  # [{question_index, chosen, time_used}]


# ── ADMIN: GÜNLÜK OYUN YÖNETİMİ ─────────────────────────────────────────────

@router.get("/calendar")
def get_calendar(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("daily_games")
        .select("*")
        .eq("institution_id", current.institution_id)
        .order("game_date", desc=True)
        .limit(60)
        .execute()
    )
    return res.data


@router.post("/calendar")
def create_daily_game(body: DailyGameCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Aynı gün için var mı?
    existing = (
        sb.table("daily_games")
        .select("id")
        .eq("institution_id", current.institution_id)
        .eq("game_date", body.game_date)
        .limit(1)
        .execute()
    )

    # Soruları UUID listesi yerine JSON olarak saklayacağız (game_metadata sütunu yok,
    # password sütununu kullanacağız + sorular için ayrı tablo yerine hint alanına JSON)
    # Sorular için game_questions tablosunu kullan
    question_ids = []
    for q in body.questions:
        qres = sb.table("game_questions").insert({
            "institution_id": current.institution_id,
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "time_seconds": q.time_seconds,
            "hint": q.player_type,  # hint alanını player_type için kullanıyoruz
        }).execute()
        question_ids.append(qres.data[0]["id"])

    data = {
        "institution_id": current.institution_id,
        "game_date": body.game_date,
        "password": body.password.upper().strip(),
        "question_ids": question_ids,
        "open_time": body.open_time,
        "close_time": body.close_time,
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


@router.get("/calendar/{game_id}/participants")
def get_participants(game_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    game_res = sb.table("daily_games").select("*").eq("id", game_id).eq("institution_id", current.institution_id).limit(1).execute()
    if not game_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oyun bulunamadı")
    game = game_res.data[0]

    # Sınıf filtresi varsa
    if game.get("speed_bonus_enabled") is not None:  # classroom_id yoksa tüm öğrenciler
        students = (
            sb.table("students")
            .select("id,first_name,last_name,parent_first_name,parent_last_name,parent_phone")
            .eq("institution_id", current.institution_id)
            .eq("status", "approved")
            .execute()
        )
    else:
        students = (
            sb.table("students")
            .select("id,first_name,last_name,parent_first_name,parent_last_name,parent_phone")
            .eq("institution_id", current.institution_id)
            .eq("status", "approved")
            .execute()
        )

    return {"game": game, "students": students.data}


# ── PUBLIC: OYUN SAYFASI ─────────────────────────────────────────────────────

@router.get("/play/{game_id}")
def get_game_public(game_id: str):
    """Oyun sayfası için veri. Doğru cevapları gönderme."""
    sb = get_supabase()
    res = sb.table("daily_games").select("*").eq("id", game_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oyun bulunamadı")
    game = res.data[0]

    # Soruları çek (doğru cevap YOK)
    questions = []
    for qid in (game.get("question_ids") or []):
        qres = sb.table("game_questions").select(
            "id,question_text,option_a,option_b,option_c,option_d,time_seconds,hint"
        ).eq("id", qid).limit(1).execute()
        if qres.data:
            q = qres.data[0]
            questions.append({
                "id": q["id"],
                "question_text": q["question_text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "time_seconds": q["time_seconds"],
                "player_type": q.get("hint", "child"),  # hint=player_type
            })

    child_questions = [q for q in questions if q["player_type"] == "child"]
    parent_questions = [q for q in questions if q["player_type"] == "parent"]

    return {
        "id": game["id"],
        "game_date": game["game_date"],
        "open_time": game["open_time"],
        "close_time": game["close_time"],
        "institution_id": game["institution_id"],
        "child_questions": child_questions,
        "parent_questions": parent_questions,
    }


@router.post("/play/{game_id}/verify-password")
def verify_password(game_id: str, body: dict):
    """Şifre doğrulama."""
    sb = get_supabase()
    res = sb.table("daily_games").select("password,institution_id").eq("id", game_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oyun bulunamadı")
    
    correct = res.data[0]["password"].upper().strip()
    entered = str(body.get("password", "")).upper().strip()
    
    if correct != entered:
        return {"correct": False, "student_name": None, "parent_name": None}
    
    # Öğrenciyi bul (telefon numarasından)
    phone = str(body.get("phone", ""))
    student_name = None
    parent_name = None
    
    if phone:
        student_res = (
            sb.table("students")
            .select("first_name,last_name,parent_first_name,parent_last_name")
            .eq("institution_id", res.data[0]["institution_id"])
            .eq("parent_phone", phone)
            .limit(1)
            .execute()
        )
        if student_res.data:
            s = student_res.data[0]
            student_name = f"{s['first_name']} {s['last_name']}"
            parent_name = f"{s['parent_first_name']} {s['parent_last_name']}"
    
    return {"correct": True, "student_name": student_name, "parent_name": parent_name}


@router.post("/play/{game_id}/submit")
def submit_answers(game_id: str, body: AnswerSubmit):
    """Cevapları kaydet ve puanı hesapla."""
    sb = get_supabase()
    
    # Oyunu al
    game_res = sb.table("daily_games").select("*").eq("id", game_id).limit(1).execute()
    if not game_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oyun bulunamadı")
    game = game_res.data[0]
    
    # Doğru cevapları al
    question_ids = game.get("question_ids") or []
    correct_map = {}
    for qid in question_ids:
        qres = sb.table("game_questions").select("id,correct_option,time_seconds,hint").eq("id", qid).limit(1).execute()
        if qres.data:
            q = qres.data[0]
            correct_map[q["id"]] = {
                "correct": q["correct_option"].upper(),
                "time_seconds": q["time_seconds"],
                "player_type": q.get("hint", "child")
            }
    
    child_q_ids = [qid for qid in question_ids if correct_map.get(qid, {}).get("player_type") == "child"]
    parent_q_ids = [qid for qid in question_ids if correct_map.get(qid, {}).get("player_type") == "parent"]
    
    # Puan hesapla
    total_score = 0
    breakdown = []
    
    for i, ans in enumerate(body.child_answers):
        if i >= len(child_q_ids):
            break
        qid = child_q_ids[i]
        info = correct_map.get(qid, {})
        chosen = str(ans.get("chosen", "")).upper()
        time_used = int(ans.get("time_used", 0))
        is_correct = chosen == info.get("correct")
        
        pts = 0
        if is_correct:
            pts = 100
            max_t = info.get("time_seconds", 30)
            if time_used <= max_t / 2:
                pts += 20  # hız bonusu
        else:
            pts = 10  # katılım
        
        total_score += pts
        breakdown.append({"player": "child", "qid": qid, "chosen": chosen,
                          "correct": info.get("correct"), "is_correct": is_correct, "score": pts})
    
    for i, ans in enumerate(body.parent_answers):
        if i >= len(parent_q_ids):
            break
        qid = parent_q_ids[i]
        info = correct_map.get(qid, {})
        chosen = str(ans.get("chosen", "")).upper()
        time_used = int(ans.get("time_used", 0))
        is_correct = chosen == info.get("correct")
        
        pts = 0
        if is_correct:
            pts = 100
            max_t = info.get("time_seconds", 30)
            if time_used <= max_t / 2:
                pts += 20
        else:
            pts = 10
        
        # Veli x1.5 çarpan
        pts = int(pts * 1.5)
        total_score += pts
        breakdown.append({"player": "parent", "qid": qid, "chosen": chosen,
                          "correct": info.get("correct"), "is_correct": is_correct, "score": pts})
    
    # Öğrenciyi bul
    student_res = (
        sb.table("students")
        .select("id,first_name,last_name,parent_first_name,parent_last_name")
        .eq("institution_id", game["institution_id"])
        .eq("parent_phone", body.parent_phone)
        .limit(1)
        .execute()
    )
    
    student_id = None
    student_name = body.parent_phone
    parent_name = ""
    
    if student_res.data:
        s = student_res.data[0]
        student_id = s["id"]
        student_name = f"{s['first_name']} {s['last_name']}"
        parent_name = f"{s['parent_first_name']} {s['parent_last_name']}"
    
    # Daha önce oynamış mı?
    if student_id:
        existing = (
            sb.table("game_sessions")
            .select("id,total_score")
            .eq("daily_game_id", game_id)
            .eq("student_id", student_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return {
                "already_played": True,
                "total_score": existing.data[0]["total_score"],
                "student_name": student_name,
                "parent_name": parent_name,
                "breakdown": []
            }
        
        sb.table("game_sessions").insert({
            "institution_id": game["institution_id"],
            "daily_game_id": game_id,
            "student_id": student_id,
            "child_answers": body.child_answers,
            "parent_answers": body.parent_answers,
            "total_score": total_score,
            "score_breakdown": breakdown,
        }).execute()
    
    return {
        "already_played": False,
        "total_score": total_score,
        "student_name": student_name,
        "parent_name": parent_name,
        "breakdown": breakdown
    }


@router.get("/play/{game_id}/leaderboard")
def get_leaderboard(game_id: str):
    sb = get_supabase()
    res = (
        sb.table("game_sessions")
        .select("total_score,student_id,students(first_name,last_name)")
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
