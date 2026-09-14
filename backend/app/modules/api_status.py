"""Modulo API Status: monitoraggio periodico della raggiungibilità di un
elenco di API esterne (stile "status page").

Ruoli:
  - "user": accesso in sola lettura alla dashboard.
  - "manager": può inoltre inserire/modificare/eliminare le API monitorate
    e forzare un controllo immediato.

Un endpoint pubblico (`GET /public`) espone lo stato corrente senza
autenticazione, per una status page consultabile da chiunque.
"""

import fcntl
import logging
import threading
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..config import BASE_DIR
from ..database import Base, SessionLocal, engine
from ..datetime_utils import UtcDatetime
from ..deps import get_db, require_module_role

logger = logging.getLogger("blattaforma.api_status")

MODULE_NAME = "api-status"
MODULE_LABEL = "API Status"
MODULE_ROLES = ["user", "manager"]

router = APIRouter()


# ---------- DB model ----------


class ApiStatusTarget(Base):
    __tablename__ = "api_status_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    expected_status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ---------- Schemas ----------


def _validate_http_url(value: str | None) -> str | None:
    if value is not None and not value.startswith(("http://", "https://")):
        raise ValueError("L'URL deve iniziare con http:// o https://")
    return value


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    expected_status_code: int = Field(default=200, ge=100, le=599)
    check_interval_seconds: int = Field(default=60, ge=10, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    enabled: bool = True

    _check_url = field_validator("url")(_validate_http_url)


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    expected_status_code: int | None = Field(default=None, ge=100, le=599)
    check_interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None

    _check_url = field_validator("url")(_validate_http_url)


class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    expected_status_code: int
    check_interval_seconds: int
    timeout_seconds: int
    enabled: bool
    last_checked_at: UtcDatetime | None
    last_status: str
    last_status_code: int | None
    last_response_time_ms: int | None
    last_error: str | None


class PublicTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    enabled: bool
    last_checked_at: UtcDatetime | None
    last_status: str
    last_response_time_ms: int | None


# ---------- Helpers ----------


def _require_manager(roles: list[str]) -> None:
    if "manager" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Richiesto il ruolo 'manager'")


def _get_target_or_404(db: Session, target_id: int) -> ApiStatusTarget:
    target = db.query(ApiStatusTarget).filter(ApiStatusTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API non trovata")
    return target


# ---------- Endpoints ----------


@router.get("", response_model=list[TargetOut])
def list_targets(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    return db.query(ApiStatusTarget).order_by(ApiStatusTarget.name).all()


@router.get("/public", response_model=list[PublicTargetOut])
def list_public_targets(db: Session = Depends(get_db)):
    return (
        db.query(ApiStatusTarget)
        .filter(ApiStatusTarget.enabled.is_(True))
        .order_by(ApiStatusTarget.name)
        .all()
    )


@router.post("", response_model=TargetOut, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: TargetCreate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_manager(roles)
    target = ApiStatusTarget(**payload.model_dump())
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


@router.patch("/{target_id}", response_model=TargetOut)
def update_target(
    target_id: int,
    payload: TargetUpdate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_manager(roles)
    target = _get_target_or_404(db, target_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    db.commit()
    db.refresh(target)
    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(
    target_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_manager(roles)
    target = _get_target_or_404(db, target_id)
    db.delete(target)
    db.commit()


@router.post("/{target_id}/check", response_model=TargetOut)
def check_target_now(
    target_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_manager(roles)
    target = _get_target_or_404(db, target_id)
    _check_target(target)
    db.commit()
    db.refresh(target)
    return target


# ---------- Controllo periodico in background ----------
#
# Un thread daemon, avviato una volta per processo, controlla a rotazione le
# API abilitate rispettando l'intervallo configurato per ciascuna. Poiché il
# backend gira con più worker uvicorn, i thread si contendono un file lock e
# solo quello che lo ottiene esegue davvero i controlli (gli altri riprovano
# finché il leader non muore), come nello scheduler del modulo Ollama.

_SCHEDULER_LOCK_PATH = str(BASE_DIR / "api_status_scheduler.lock")
_SCHEDULER_TICK_SECONDS = 15
_scheduler_lock_fh = None
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _acquire_scheduler_lock():
    global _scheduler_lock_fh
    fh = open(_SCHEDULER_LOCK_PATH, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    _scheduler_lock_fh = fh
    return fh


def _scheduler_loop() -> None:
    while _acquire_scheduler_lock() is None:
        time.sleep(60)

    logger.info("API Status: scheduler dei controlli avviato")
    while True:
        try:
            _check_due_targets()
        except Exception:
            logger.exception("API Status: giro di controlli fallito")
        time.sleep(_SCHEDULER_TICK_SECONDS)


def _check_due_targets() -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        targets = db.query(ApiStatusTarget).filter(ApiStatusTarget.enabled.is_(True)).all()
        due = [
            t
            for t in targets
            if t.last_checked_at is None
            or (now - t.last_checked_at).total_seconds() >= t.check_interval_seconds
        ]
        if not due:
            return
        for target in due:
            _check_target(target)
        db.commit()
    finally:
        db.close()


def _check_target(target: ApiStatusTarget) -> None:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=target.timeout_seconds, follow_redirects=True) as client:
            resp = client.get(target.url)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        target.last_status_code = resp.status_code
        target.last_response_time_ms = elapsed_ms
        if resp.status_code == target.expected_status_code:
            target.last_status = "up"
            target.last_error = None
        else:
            target.last_status = "down"
            target.last_error = (
                f"Status code {resp.status_code} diverso da quello atteso ({target.expected_status_code})"
            )
    except Exception as exc:
        target.last_status = "down"
        target.last_status_code = None
        target.last_response_time_ms = None
        target.last_error = str(exc)[:500]
    target.last_checked_at = datetime.utcnow()


def _start_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=_scheduler_loop, name="api-status-scheduler", daemon=True).start()


Base.metadata.create_all(bind=engine)
_start_scheduler()
