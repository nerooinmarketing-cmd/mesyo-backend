"""
Modül yönetimi. `modules` tablosu sabit/global liste (seed data ile gelir).
`institution_modules` tablosu kurum bazlı aç/kapat durumunu tutar — burada
satır olmayan modüller varsayılan olarak `modules.is_default` değerini alır.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.deps import require_role, require_institution, CurrentUser

router = APIRouter(prefix="/modules", tags=["modules"])
_superadmin_only = require_role("superadmin")


class ModuleToggle(BaseModel):
    module_id: str
    is_active: bool


class BulkModuleUpdate(BaseModel):
    updates: list[ModuleToggle]


def _merge_with_defaults(all_modules: list[dict], institution_overrides: list[dict]) -> dict[str, bool]:
    """modules.is_default + institution_modules.is_active satırlarını birleştirir.
    institution_modules'de satır varsa o öncelikli, yoksa modules.is_default kullanılır."""
    override_map = {row["module_id"]: row["is_active"] for row in institution_overrides}
    return {m["id"]: override_map.get(m["id"], m["is_default"]) for m in all_modules}


@router.get("/all")
def list_all_modules(current: CurrentUser = Depends(require_institution)):
    """Sabit modül kataloğu — herhangi bir oturum açmış kullanıcı görebilir (UI bunu kullanır)."""
    sb = get_supabase()
    res = sb.table("modules").select("*").execute()
    return res.data


@router.get("/institution/{institution_id}")
def get_institution_modules(institution_id: str, current: CurrentUser = Depends(_superadmin_only)):
    """Superadmin'in Modül Yönetimi sayfası bunu kullanır — { module_id: bool } şeklinde."""
    sb = get_supabase()
    all_modules = sb.table("modules").select("*").execute().data
    overrides = (
        sb.table("institution_modules").select("module_id, is_active")
        .eq("institution_id", institution_id).execute().data
    )
    return _merge_with_defaults(all_modules, overrides)


@router.post("/institution/{institution_id}")
def update_institution_modules(institution_id: str, body: BulkModuleUpdate, current: CurrentUser = Depends(_superadmin_only)):
    """Superadmin'in 'Kaydet' butonu bunu çağırır — toplu upsert."""
    sb = get_supabase()
    if not body.updates:
        return {"detail": "Güncellenecek kayıt yok"}

    rows = [
        {"institution_id": institution_id, "module_id": u.module_id, "is_active": u.is_active}
        for u in body.updates
    ]
    sb.table("institution_modules").upsert(rows, on_conflict="institution_id,module_id").execute()
    return {"detail": f"{len(rows)} modül güncellendi"}


@router.get("/my")
def my_active_modules(current: CurrentUser = Depends(require_institution)):
    """Kurum yöneticisi/öğretmen tarafı bunu kullanır — kendi kurumunun aktif modülleri.
    ModuleContext bu endpoint'i çağırarak menüyü oluşturur."""
    sb = get_supabase()
    all_modules = sb.table("modules").select("*").execute().data
    overrides = (
        sb.table("institution_modules").select("module_id, is_active")
        .eq("institution_id", current.institution_id).execute().data
    )
    return _merge_with_defaults(all_modules, overrides)
