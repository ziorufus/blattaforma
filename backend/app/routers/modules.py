from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models
from ..deps import get_current_user, get_db, require_admin
from ..schemas import ModuleOut, ModuleWithAccessOut

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleWithAccessOut])
def list_my_modules(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modules the current user has at least some access to (drives the frontend menu)."""
    effective = crud.effective_permissions(db, user)
    modules = db.query(models.Module).order_by(models.Module.label).all()
    return [
        ModuleWithAccessOut(
            id=m.id, name=m.name, label=m.label, roles=m.roles, granted_roles=effective.get(m.name, [])
        )
        for m in modules
        if effective.get(m.name)
    ]


@router.get("/all", response_model=list[ModuleOut], dependencies=[Depends(require_admin)])
def list_all_modules(db: Session = Depends(get_db)):
    """Full module catalog, for the admin permission-assignment screens."""
    return db.query(models.Module).order_by(models.Module.label).all()
