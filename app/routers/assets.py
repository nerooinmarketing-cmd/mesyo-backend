"""
Demirbaş (asset) yönetimi. Kod (DMB-001 vb.) otomatik üretilir — SQL şemasındaki
generate_asset_code() fonksiyonu RPC ile çağrılır, mantığı burada tekrar yazmıyoruz.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_institution, CurrentUser

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetCreate(BaseModel):
    name: str
    category: str = "diger"
    condition: str = "iyi"
    quantity: int = 1
    unit: str = "Adet"
    location: str | None = None
    purchase_date: str | None = None
    purchase_price: float | None = None
    supplier: str | None = None
    serial_no: str | None = None
    next_maintenance: str | None = None
    note: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    condition: str | None = None
    quantity: int | None = None
    unit: str | None = None
    location: str | None = None
    purchase_date: str | None = None
    purchase_price: float | None = None
    supplier: str | None = None
    serial_no: str | None = None
    last_maintenance: str | None = None
    next_maintenance: str | None = None
    note: str | None = None


class MaintenanceLogCreate(BaseModel):
    maintenance_type: str  # 'bakim' | 'tamir' | 'degisim'
    log_date: str
    note: str
    cost: float | None = None


@router.get("")
def list_assets(current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("assets").select("*")
        .eq("institution_id", current.institution_id)
        .order("code")
        .execute()
    )
    return res.data


@router.post("")
def create_asset(body: AssetCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()

    # Kod üretimi SQL fonksiyonunda (generate_asset_code) — tekrar yazmıyoruz.
    code_res = sb.rpc("generate_asset_code", {"p_institution_id": current.institution_id}).execute()
    code = code_res.data

    data = body.model_dump(exclude_none=True)
    data["institution_id"] = current.institution_id
    data["code"] = code

    res = sb.table("assets").insert(data).execute()
    return res.data[0]


@router.patch("/{asset_id}")
def update_asset(asset_id: str, body: AssetUpdate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Güncellenecek alan yok")

    res = (
        sb.table("assets").update(data)
        .eq("id", asset_id).eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demirbaş bulunamadı")
    return res.data[0]


@router.delete("/{asset_id}")
def delete_asset(asset_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    res = (
        sb.table("assets").delete()
        .eq("id", asset_id).eq("institution_id", current.institution_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demirbaş bulunamadı")
    return {"detail": "Silindi"}


@router.get("/maintenance-logs")
def list_all_maintenance_logs(current: CurrentUser = Depends(require_institution)):
    """Rapor sekmesi için — kurumun TÜM demirbaşlarının bakım geçmişi, tek seferde."""
    sb = get_supabase()
    asset_ids_res = (
        sb.table("assets").select("id")
        .eq("institution_id", current.institution_id)
        .execute()
    )
    asset_ids = [a["id"] for a in asset_ids_res.data]
    if not asset_ids:
        return []
    res = (
        sb.table("asset_maintenance_logs").select("*")
        .in_("asset_id", asset_ids)
        .order("log_date", desc=True)
        .execute()
    )
    return res.data


@router.get("/{asset_id}/maintenance-logs")
def list_maintenance_logs(asset_id: str, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    # Demirbaşın bu kuruma ait olduğunu doğrula
    asset_check = (
        sb.table("assets").select("id")
        .eq("id", asset_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not asset_check.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demirbaş bulunamadı")

    res = (
        sb.table("asset_maintenance_logs").select("*")
        .eq("asset_id", asset_id)
        .order("log_date", desc=True)
        .execute()
    )
    return res.data


@router.post("/{asset_id}/maintenance-logs")
def add_maintenance_log(asset_id: str, body: MaintenanceLogCreate, current: CurrentUser = Depends(require_institution)):
    sb = get_supabase()
    asset_check = (
        sb.table("assets").select("id, condition")
        .eq("id", asset_id).eq("institution_id", current.institution_id)
        .limit(1).execute()
    )
    if not asset_check.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demirbaş bulunamadı")

    data = body.model_dump()
    data["asset_id"] = asset_id
    data["created_by"] = current.id
    log_res = sb.table("asset_maintenance_logs").insert(data).execute()

    # Bakım veya tamir kaydı eklenince demirbaşın durumu otomatik "iyi"ye döner —
    # ve bakım tipindeyse last_maintenance güncellenir (frontend'deki davranışla aynı).
    if body.maintenance_type in ("bakim", "tamir"):
        update_data = {"condition": "iyi"}
        if body.maintenance_type == "bakim":
            update_data["last_maintenance"] = body.log_date
        sb.table("assets").update(update_data).eq("id", asset_id).execute()

    return log_res.data[0]
