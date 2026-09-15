"""macOS daemons module: lets enabled users start/stop/enable/disable
LaunchDaemons on a fleet of registered Mac machines, without SSH.

Every machine runs a small root-only helper (see helpers/macos-daemons/ in
the repo) fronted by nginx on a fixed port. This module never talks to
launchctl directly: it proxies action requests to that helper, which is the
only place that knows the real, root-only whitelist of allowed daemons. The
`DaemonDefinition` rows kept here are just a UI-facing mirror of that
whitelist -- adding one here does not by itself grant any new capability on
the machine.
"""

import logging
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from .. import models
from ..database import Base, engine
from ..datetime_utils import UtcDatetime
from ..deps import get_current_user, get_db, require_module_role

logger = logging.getLogger("blattaforma.modules.macos_daemons")

MODULE_NAME = "macos-daemons"
MODULE_LABEL = "Demoni macOS"
MODULE_ROLES = ["operate"]

MACOS_DAEMONS_PORT = 11437
CONTROL_TIMEOUT = 10.0

SLUG_PATTERN = r"^[a-z0-9-]+$"
LABEL_PATTERN = r"^[A-Za-z0-9._-]+$"

ACTIONS = ("start", "stop", "enable", "disable")

router = APIRouter()


# ---------- DB models ----------


class DaemonMachine(Base):
    __tablename__ = "macos_daemon_machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    control_key: Mapped[str] = mapped_column(String(512), nullable=False)


class DaemonDefinition(Base):
    __tablename__ = "macos_daemon_definitions"
    __table_args__ = (UniqueConstraint("machine_id", "label", name="uq_daemon_machine_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("macos_daemon_machines.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plist_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class DaemonActionLog(Base):
    __tablename__ = "macos_daemon_action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    message: Mapped[str | None] = mapped_column(String(2048), nullable=True)


# ---------- Schemas ----------


class MachineCreate(BaseModel):
    name: str
    slug: str = Field(pattern=SLUG_PATTERN)
    ip_address: str
    control_key: str


class MachineUpdate(BaseModel):
    name: str | None = None
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    ip_address: str | None = None
    control_key: str | None = None


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    ip_address: str


class DaemonDefinitionCreate(BaseModel):
    label: str = Field(pattern=LABEL_PATTERN)
    display_name: str
    plist_path: str


class DaemonDefinitionUpdate(BaseModel):
    display_name: str | None = None
    plist_path: str | None = None


class DaemonStatusOut(BaseModel):
    id: int
    machine_id: int
    label: str
    display_name: str
    plist_path: str
    loaded: bool | None = None
    running: bool | None = None
    enabled: bool | None = None
    error: str | None = None


class ActionResult(BaseModel):
    success: bool
    message: str | None = None


class ActionLogEntry(BaseModel):
    created_at: UtcDatetime
    machine_name: str
    label: str
    action: str
    user_email: str | None = None
    success: bool
    message: str | None = None


# ---------- Helpers ----------


def _to_machine_out(machine: DaemonMachine) -> MachineOut:
    return MachineOut(id=machine.id, name=machine.name, slug=machine.slug, ip_address=machine.ip_address)


def _get_machine_or_404(db: Session, machine_id: int) -> DaemonMachine:
    machine = db.query(DaemonMachine).filter(DaemonMachine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Macchina non trovata")
    return machine


def _check_slug_unique(db: Session, slug: str, exclude_id: int | None = None) -> None:
    query = db.query(DaemonMachine).filter(DaemonMachine.slug == slug)
    if exclude_id is not None:
        query = query.filter(DaemonMachine.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esiste già una macchina con questo ID",
        )


def _require_role(roles: list[str], role: str) -> None:
    if role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Richiesto il ruolo '{role}'")


def _get_definition_or_404(db: Session, machine_id: int, daemon_id: int) -> DaemonDefinition:
    definition = (
        db.query(DaemonDefinition)
        .filter(DaemonDefinition.id == daemon_id, DaemonDefinition.machine_id == machine_id)
        .first()
    )
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demone non trovato")
    return definition


def _check_label_unique(db: Session, machine_id: int, label: str, exclude_id: int | None = None) -> None:
    query = db.query(DaemonDefinition).filter(
        DaemonDefinition.machine_id == machine_id, DaemonDefinition.label == label
    )
    if exclude_id is not None:
        query = query.filter(DaemonDefinition.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Questa macchina ha già un demone con questa label",
        )


def _auth_header(control_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {control_key}"}


def _log_action(
    db: Session,
    machine_id: int,
    label: str,
    action: str,
    user_id: int,
    success: bool,
    message: str | None,
) -> None:
    db.add(
        DaemonActionLog(
            machine_id=machine_id,
            label=label,
            action=action,
            user_id=user_id,
            success=success,
            message=(message or "")[:2048] or None,
        )
    )
    db.commit()


async def _call_daemon_action(machine: DaemonMachine, label: str, action: str) -> ActionResult:
    try:
        async with httpx.AsyncClient(timeout=CONTROL_TIMEOUT) as client:
            resp = await client.post(
                f"http://{machine.ip_address}:{MACOS_DAEMONS_PORT}/{action}",
                json={"label": label},
                headers=_auth_header(machine.control_key),
            )
    except httpx.HTTPError as exc:
        return ActionResult(success=False, message=f"Macchina non raggiungibile: {exc}")

    if resp.status_code != 200:
        return ActionResult(success=False, message=f"HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    message = data.get("stderr") or data.get("stdout") or None
    return ActionResult(success=bool(data.get("success")), message=message)


async def _call_daemon_status(machine: DaemonMachine, label: str) -> dict:
    async with httpx.AsyncClient(timeout=CONTROL_TIMEOUT) as client:
        resp = await client.post(
            f"http://{machine.ip_address}:{MACOS_DAEMONS_PORT}/status",
            json={"label": label},
            headers=_auth_header(machine.control_key),
        )
    resp.raise_for_status()
    return resp.json()


async def _to_status_out(machine: DaemonMachine, definition: DaemonDefinition) -> DaemonStatusOut:
    out = DaemonStatusOut(
        id=definition.id,
        machine_id=definition.machine_id,
        label=definition.label,
        display_name=definition.display_name,
        plist_path=definition.plist_path,
    )
    try:
        data = await _call_daemon_status(machine, definition.label)
        out.loaded = data.get("loaded")
        out.running = data.get("running")
        out.enabled = data.get("enabled")
    except httpx.HTTPError as exc:
        out.error = f"Macchina non raggiungibile: {exc}"
    return out


# ---------- Machines CRUD (role: operate) ----------


@router.get("/machines", response_model=list[MachineOut])
def list_machines(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    return [_to_machine_out(m) for m in db.query(DaemonMachine).order_by(DaemonMachine.id).all()]


@router.post("/machines", response_model=MachineOut, status_code=status.HTTP_201_CREATED)
def create_machine(
    payload: MachineCreate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    _check_slug_unique(db, payload.slug)
    machine = DaemonMachine(**payload.model_dump())
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return _to_machine_out(machine)


@router.patch("/machines/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: int,
    payload: MachineUpdate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)

    data = payload.model_dump(exclude_unset=True)
    if data.get("slug"):
        _check_slug_unique(db, data["slug"], exclude_id=machine.id)
    for field in ("name", "slug", "ip_address", "control_key"):
        if data.get(field):
            setattr(machine, field, data[field])

    db.commit()
    db.refresh(machine)
    return _to_machine_out(machine)


@router.delete("/machines/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(
    machine_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)
    db.delete(machine)
    db.commit()


# ---------- Daemon definitions (role: operate) ----------


@router.get("/machines/{machine_id}/daemons", response_model=list[DaemonStatusOut])
async def list_daemons(
    machine_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)
    definitions = (
        db.query(DaemonDefinition)
        .filter(DaemonDefinition.machine_id == machine_id)
        .order_by(DaemonDefinition.display_name)
        .all()
    )
    return [await _to_status_out(machine, d) for d in definitions]


@router.post(
    "/machines/{machine_id}/daemons",
    response_model=DaemonStatusOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_daemon(
    machine_id: int,
    payload: DaemonDefinitionCreate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)
    _check_label_unique(db, machine_id, payload.label)
    definition = DaemonDefinition(machine_id=machine_id, **payload.model_dump())
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return await _to_status_out(machine, definition)


@router.patch("/machines/{machine_id}/daemons/{daemon_id}", response_model=DaemonStatusOut)
async def update_daemon(
    machine_id: int,
    daemon_id: int,
    payload: DaemonDefinitionUpdate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)
    definition = _get_definition_or_404(db, machine_id, daemon_id)

    data = payload.model_dump(exclude_unset=True)
    for field in ("display_name", "plist_path"):
        if data.get(field):
            setattr(definition, field, data[field])

    db.commit()
    db.refresh(definition)
    return await _to_status_out(machine, definition)


@router.delete("/machines/{machine_id}/daemons/{daemon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_daemon(
    machine_id: int,
    daemon_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    _get_machine_or_404(db, machine_id)
    definition = _get_definition_or_404(db, machine_id, daemon_id)
    db.delete(definition)
    db.commit()


# ---------- Actions (role: operate) ----------


@router.post("/machines/{machine_id}/daemons/{daemon_id}/{action}", response_model=ActionResult)
async def run_daemon_action(
    machine_id: int,
    daemon_id: int,
    action: Literal["start", "stop", "enable", "disable"],
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)
    definition = _get_definition_or_404(db, machine_id, daemon_id)

    result = await _call_daemon_action(machine, definition.label, action)
    _log_action(db, machine.id, definition.label, action, user.id, result.success, result.message)
    return result


@router.get("/machines/{machine_id}/daemons/{daemon_id}/status", response_model=DaemonStatusOut)
async def get_daemon_status(
    machine_id: int,
    daemon_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    machine = _get_machine_or_404(db, machine_id)
    definition = _get_definition_or_404(db, machine_id, daemon_id)
    return await _to_status_out(machine, definition)


# ---------- Action log (role: operate) ----------


@router.get("/logs", response_model=list[ActionLogEntry])
def list_action_log(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "operate")
    rows = (
        db.query(DaemonActionLog, DaemonMachine.name, models.User.email)
        .join(DaemonMachine, DaemonMachine.id == DaemonActionLog.machine_id)
        .outerjoin(models.User, models.User.id == DaemonActionLog.user_id)
        .order_by(DaemonActionLog.id.desc())
        .limit(200)
        .all()
    )
    return [
        ActionLogEntry(
            created_at=log.created_at,
            machine_name=machine_name,
            label=log.label,
            action=log.action,
            user_email=user_email,
            success=log.success,
            message=log.message,
        )
        for log, machine_name, user_email in rows
    ]


# ---------- Token check (public, called by nginx auth_request on the Mac) ----------
#
# Mirrors ollama's /check in spirit but is simpler: one control_key per
# machine (no read/write split), since every action here is equally
# sensitive. `Code` is the machine's slug, hardcoded in that machine's own
# nginx snippet (same convention as nginx-conf/ollama).


@router.get("/check", status_code=status.HTTP_204_NO_CONTENT)
def check_control_key(
    authorization: str | None = Header(default=None),
    code: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    match = (
        db.query(DaemonMachine.id)
        .filter(DaemonMachine.slug == code, DaemonMachine.control_key == token)
        .first()
    )
    if not match:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


Base.metadata.create_all(bind=engine)
