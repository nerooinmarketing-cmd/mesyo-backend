"""
Sezon yönetimi. Bir kurumda aynı anda sadece 1 aktif sezon olabilir
(bkz. mesyo_soft_schema.sql — idx_one_active_season_per_institution unique index).
Yeni sezon oluşturulunca eskisi otomatik arşivlenir.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/seasons", tags=["seasons"])


class SeasonCreate(BaseModel):
    name: str
    year: int


@router.get("")
def list_seasons(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("seasons")
        .select("*")
        .eq("institution_id", current.institution_id)
        .order("year", desc=True)
        .execute()
    )
    return res.data


@router.post("")
def create_season(body: SeasonCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Mevcut aktif sezonu pasifleştir — DB'deki unique index zaten bunu zorunlu kılıyor,
    # ama burada yapmazsak insert hata verir, o yüzden önce biz hallediyoruz.
    sb.table("seasons").update({"is_active": False}).eq(
        "institution_id", current.institution_id
    ).eq("is_active", True).execute()

    data = {
        "institution_id": current.institution_id,
        "name": body.name,
        "year": body.year,
        "is_active": True,
    }
    res = sb.table("seasons").insert(data).execute()
    return res.data[0]


@router.post("/{season_id}/archive")
def archive_season(season_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("seasons")
        .update({"is_active": False, "archived_at": "now()"})
        .eq("id", season_id)
        .eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sezon bulunamadı")
    return res.data[0]
