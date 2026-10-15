from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import models, options
from ..deps import get_db, require_admin
from ..schemas import OptionOut, OptionScopeOut, OptionValueUpdate, PublicConfigOut

router = APIRouter(prefix="/api/options", tags=["options"])


@router.get("/public", response_model=PublicConfigOut)
def get_public_config(db: Session = Depends(get_db)):
    """Letto dal frontend prima di ogni altra cosa, anche senza login: le
    opzioni pubbliche e i moduli attivi (per nascondere pulsanti di login e
    pagine pubbliche dei moduli disattivati)."""
    enabled = db.query(models.Module).filter(models.Module.enabled.is_(True)).all()
    return PublicConfigOut(
        options=options.public_options(db),
        enabled_modules=sorted(m.name for m in enabled),
    )


@router.get("", response_model=list[OptionScopeOut], dependencies=[Depends(require_admin)])
def list_options(db: Session = Depends(get_db)):
    """Le opzioni globali, poi un gruppo per ogni modulo noto al DB (anche
    senza opzioni, per poterlo attivare/disattivare)."""
    scopes = [
        OptionScopeOut(
            scope=options.GLOBAL_SCOPE,
            label="Generali",
            is_module=False,
            enabled=True,
            options=options.describe_scope(db, options.GLOBAL_SCOPE),
        )
    ]
    for module in db.query(models.Module).order_by(models.Module.label).all():
        has_options = options.get_schema(module.name) is not None
        scopes.append(
            OptionScopeOut(
                scope=module.name,
                label=module.label,
                is_module=True,
                enabled=module.enabled,
                options=options.describe_scope(db, module.name) if has_options else [],
            )
        )
    return scopes


def _option_out(db: Session, scope: str, key: str) -> OptionOut:
    item = next(o for o in options.describe_scope(db, scope) if o["key"] == key)
    return OptionOut(**item)


@router.put("/{scope}/{key}", response_model=OptionOut)
def update_option(
    scope: str,
    key: str,
    payload: OptionValueUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    try:
        options.set_option(db, scope, key, payload.value, admin)
    except options.UnknownOptionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opzione non trovata")
    except ValidationError as exc:
        messages = "; ".join(err["msg"] for err in exc.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Valore non valido: {messages}"
        )
    return _option_out(db, scope, key)


@router.delete("/{scope}/{key}", response_model=OptionOut, dependencies=[Depends(require_admin)])
def reset_option(scope: str, key: str, db: Session = Depends(get_db)):
    """Ripristina il default del codice cancellando il valore salvato."""
    try:
        options.reset_option(db, scope, key)
    except options.UnknownOptionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opzione non trovata")
    return _option_out(db, scope, key)
