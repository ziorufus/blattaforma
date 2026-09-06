"""Ollama module: manages a fleet of machines running Ollama and lets
enabled users inspect loaded models / RAM usage, load an already-downloaded
model into RAM, and (for machines with a write key) pull new models.

Machine API keys are stored server-side only and never serialized back to
the frontend: every call to a machine's Ollama instance is proxied through
this router, which attaches the key as an `Authorization: Bearer ...` header.
"""

import fcntl
import logging
import math
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from .. import models
from ..config import BASE_DIR, settings
from ..database import Base, SessionLocal, engine
from ..datetime_utils import UtcDatetime
from ..deps import get_current_user, get_db, require_module_role

logger = logging.getLogger("blattaforma.modules.ollama")

MODULE_NAME = "ollama"
MODULE_LABEL = "Ollama"
MODULE_ROLES = ["machines", "models", "standard"]

OLLAMA_READ_PORT = 11435
OLLAMA_WRITE_PORT = 11436
NODE_EXPORTER_PORT = 9100

SLUG_PATTERN = r"^[a-z0-9-]+$"

# Timeout (in secondi) per le chiamate httpx verso le macchine Ollama.
AUTH_CHECK_TIMEOUT = 5.0
STATUS_TIMEOUT = 5.0
LOAD_MODEL_TIMEOUT = 1800.0
UNLOAD_MODEL_TIMEOUT = 30.0
PULL_MODEL_TIMEOUT = None

router = APIRouter()


# ---------- DB model ----------


class OllamaMachine(Base):
    __tablename__ = "ollama_machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_read: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_write: Mapped[str | None] = mapped_column(String(512), nullable=True)
    os: Mapped[str] = mapped_column(String(20), nullable=False)


class OllamaKey(Base):
    __tablename__ = "ollama_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    all_machines: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class OllamaPinnedModel(Base):
    """Un modello "bloccato" in RAM: caricato con keep_alive=-1 e mantenuto
    attivo da un refresh periodico finché un utente privilegiato non lo
    sblocca o non lo espelle. Una riga con `ended_at` NULL è un blocco
    attivo; al più uno per (macchina, modello)."""

    __tablename__ = "ollama_pinned_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ollama_machines.id", ondelete="CASCADE"), nullable=False
    )
    # Nome del modello effettivamente caricato (la variante derivata con il
    # contesto nel nome, es. "qwen2.5:32b-ctx65536").
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    context_size: Mapped[int] = mapped_column(Integer, nullable=False)
    pinned_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OllamaKeyLog(Base):
    __tablename__ = "ollama_keys_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    response_code: Mapped[int] = mapped_column(Integer, nullable=False)


ollama_key_machine_association = Table(
    "ollama_keys_machines",
    Base.metadata,
    Column("key_id", Integer, ForeignKey("ollama_keys.id", ondelete="CASCADE"), primary_key=True),
    Column("machine_id", Integer, ForeignKey("ollama_machines.id", ondelete="CASCADE"), primary_key=True),
)


# ---------- Schemas ----------


class MachineCreate(BaseModel):
    name: str
    slug: str = Field(pattern=SLUG_PATTERN)
    ip_address: str
    api_key_read: str
    api_key_write: str | None = None
    os: Literal["macos", "linux"]


class MachineUpdate(BaseModel):
    name: str | None = None
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    ip_address: str | None = None
    api_key_read: str | None = None
    api_key_write: str | None = None
    os: Literal["macos", "linux"] | None = None


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    ip_address: str
    os: str
    has_write_key: bool


class KeyCreate(BaseModel):
    name: str
    value: str
    all_machines: bool = False
    active: bool = True
    machine_ids: list[int] = []
    user_id: int | None = None


class KeyUpdate(BaseModel):
    name: str | None = None
    value: str | None = None
    all_machines: bool | None = None
    active: bool | None = None
    machine_ids: list[int] | None = None
    user_id: int | None = None


class KeyOut(BaseModel):
    id: int
    name: str
    masked_value: str
    all_machines: bool
    active: bool
    machine_ids: list[int]
    machine_names: list[str]
    user_id: int | None = None
    user_email: str | None = None


class KeyDetail(BaseModel):
    id: int
    name: str
    value: str
    all_machines: bool
    active: bool
    machine_ids: list[int]
    machine_names: list[str]
    user_id: int | None = None
    user_email: str | None = None


class MyKeyOut(BaseModel):
    id: int
    name: str
    masked_value: str
    active: bool


class AssignableUser(BaseModel):
    id: int
    email: str
    name: str | None = None


class KeyValueOut(BaseModel):
    value: str


class KeyUsageEntry(BaseModel):
    created_at: UtcDatetime
    code: str
    response_code: int


class KeyUsageBucket(BaseModel):
    label: str
    total: int
    allowed: int
    denied: int


class KeyUsageOut(BaseModel):
    recent: list[KeyUsageEntry]
    hourly: list[KeyUsageBucket]
    daily: list[KeyUsageBucket]


class ModelInfo(BaseModel):
    name: str
    size_bytes: int
    context_size: int | None = None
    pinned: bool = False
    pinned_by_email: str | None = None


class MachineStatusOut(BaseModel):
    id: int
    name: str
    slug: str
    ip_address: str
    os: str
    has_write_key: bool
    total_bytes: int | None = None
    available_bytes: int | None = None
    ollama_bytes: int = 0
    gpu_percent: float | None = None
    gpu_temp_celsius: float | None = None
    gpu_power_watts: float | None = None
    loaded_models: list[ModelInfo] = []
    available_models: list[ModelInfo] = []
    error: str | None = None


class LoadModelRequest(BaseModel):
    model: str
    context_size: int = 65536


class PullModelRequest(BaseModel):
    model: str


class PinModelRequest(BaseModel):
    model: str


# ---------- Helpers ----------


def _to_machine_out(machine: OllamaMachine) -> MachineOut:
    return MachineOut(
        id=machine.id,
        name=machine.name,
        slug=machine.slug,
        ip_address=machine.ip_address,
        os=machine.os,
        has_write_key=bool(machine.api_key_write),
    )


def _get_machine_or_404(db: Session, machine_id: int) -> OllamaMachine:
    machine = db.query(OllamaMachine).filter(OllamaMachine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Macchina non trovata")
    return machine


def _check_slug_unique(db: Session, slug: str, exclude_id: int | None = None) -> None:
    query = db.query(OllamaMachine).filter(OllamaMachine.slug == slug)
    if exclude_id is not None:
        query = query.filter(OllamaMachine.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esiste già una macchina con questo ID",
        )


def _require_role(roles: list[str], role: str) -> None:
    if role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Richiesto il ruolo '{role}'")


def _get_key_or_404(db: Session, key_id: int) -> OllamaKey:
    key = db.query(OllamaKey).filter(OllamaKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chiave non trovata")
    return key


def _mask_value(value: str) -> str:
    if len(value) <= 5:
        return value
    return "•" * min(len(value) - 5, 8) + value[-5:]


def _validate_key_rule(all_machines: bool, machine_ids: list[int]) -> None:
    if not all_machines and not machine_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Specificare almeno una tra: tutte le macchine o una macchina associata",
        )


def _key_machine_ids(db: Session, key_id: int) -> list[int]:
    rows = (
        db.query(ollama_key_machine_association.c.machine_id)
        .filter(ollama_key_machine_association.c.key_id == key_id)
        .all()
    )
    return [r[0] for r in rows]


def _set_key_machines(db: Session, key_id: int, machine_ids: list[int]) -> None:
    if machine_ids:
        existing = db.query(OllamaMachine.id).filter(OllamaMachine.id.in_(machine_ids)).all()
        found_ids = {r[0] for r in existing}
        missing = set(machine_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Macchine non trovate: {sorted(missing)}",
            )

    db.execute(
        ollama_key_machine_association.delete().where(ollama_key_machine_association.c.key_id == key_id)
    )
    for machine_id in machine_ids:
        db.execute(
            ollama_key_machine_association.insert().values(key_id=key_id, machine_id=machine_id)
        )


def _key_user_email(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    row = db.query(models.User.email).filter(models.User.id == user_id).first()
    return row[0] if row else None


def _to_key_out(db: Session, key: OllamaKey) -> KeyOut:
    machine_ids = [] if key.all_machines else _key_machine_ids(db, key.id)
    machine_names = []
    if machine_ids:
        rows = db.query(OllamaMachine.name).filter(OllamaMachine.id.in_(machine_ids)).all()
        machine_names = [r[0] for r in rows]
    return KeyOut(
        id=key.id,
        name=key.name,
        masked_value=_mask_value(key.value),
        all_machines=key.all_machines,
        active=key.active,
        machine_ids=machine_ids,
        machine_names=machine_names,
        user_id=key.user_id,
        user_email=_key_user_email(db, key.user_id),
    )


def _to_key_detail(db: Session, key: OllamaKey) -> KeyDetail:
    machine_ids = [] if key.all_machines else _key_machine_ids(db, key.id)
    machine_names = []
    if machine_ids:
        rows = db.query(OllamaMachine.name).filter(OllamaMachine.id.in_(machine_ids)).all()
        machine_names = [r[0] for r in rows]
    return KeyDetail(
        id=key.id,
        name=key.name,
        value=key.value,
        all_machines=key.all_machines,
        active=key.active,
        machine_ids=machine_ids,
        machine_names=machine_names,
        user_id=key.user_id,
        user_email=_key_user_email(db, key.user_id),
    )


def _to_my_key_out(key: OllamaKey) -> MyKeyOut:
    return MyKeyOut(
        id=key.id,
        name=key.name,
        masked_value=_mask_value(key.value),
        active=key.active,
    )


def _get_own_key_or_404(db: Session, key_id: int, user_id: int) -> OllamaKey:
    key = db.query(OllamaKey).filter(OllamaKey.id == key_id, OllamaKey.user_id == user_id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chiave non trovata")
    return key


def _generate_key_value() -> str:
    return secrets.token_hex(32)


def _bucketize(
    rows: list[OllamaKeyLog], start: datetime, bucket_seconds: int, num_buckets: int
) -> list[KeyUsageBucket]:
    counts = [{"total": 0, "allowed": 0, "denied": 0} for _ in range(num_buckets)]
    for row in rows:
        idx = int((row.created_at - start).total_seconds() // bucket_seconds)
        if 0 <= idx < num_buckets:
            bucket = counts[idx]
            bucket["total"] += 1
            if row.response_code == status.HTTP_204_NO_CONTENT:
                bucket["allowed"] += 1
            else:
                bucket["denied"] += 1
    return [
        KeyUsageBucket(
            label=(start + timedelta(seconds=bucket_seconds * i)).replace(tzinfo=timezone.utc).isoformat(),
            **counts[i],
        )
        for i in range(num_buckets)
    ]


def _auth_header(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _utcnow() -> datetime:
    """Timestamp naive in UTC, coerente con la convenzione del DB (vedi datetime_utils)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _active_pin(db: Session, machine_id: int, model: str) -> OllamaPinnedModel | None:
    return (
        db.query(OllamaPinnedModel)
        .filter(
            OllamaPinnedModel.machine_id == machine_id,
            OllamaPinnedModel.model == model,
            OllamaPinnedModel.ended_at.is_(None),
        )
        .first()
    )


# The OpenAI-compatible endpoint (/v1/chat/completions, ...) has no `num_ctx`
# parameter, so a request that omits it makes Ollama reload the model at the
# default context. To avoid that, every load goes through a derived model that
# bakes `num_ctx` into its Modelfile (`PARAMETER num_ctx N`) -- Ollama honours
# that on the OpenAI endpoint too. The derived name keeps the base ref and
# appends a `-ctx<N>` marker to the tag (`qwen2.5:32b` -> `qwen2.5:32b-ctx65536`;
# a tagless ref gets `:ctx<N>`). nginx (njs + the /check service) rewrites the
# incoming model name to the loaded derived variant.

_DERIVED_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[-:]ctx(?P<ctx>\d+)$")


def _derived_model_name(model: str, num_ctx: int) -> str:
    head, sep, tag = model.rpartition(":")
    if sep and "/" not in tag:
        return f"{head}:{tag}-ctx{num_ctx}"
    return f"{model}:ctx{num_ctx}"


def _strip_derived_suffix(name: str) -> str:
    match = _DERIVED_SUFFIX_RE.match(name or "")
    return match.group("base") if match else (name or "")


def _derived_context_size(name: str) -> int | None:
    match = _DERIVED_SUFFIX_RE.match(name or "")
    return int(match.group("ctx")) if match else None


def _is_derived_model(name: str) -> bool:
    return bool(_DERIVED_SUFFIX_RE.match(name or ""))


def _match_loaded_model(ps_models: list[dict], requested: str | None) -> tuple[str | None, int | None]:
    """Return (full_name, context_length) of the loaded runner serving
    `requested`: an exact name match first, then a derived `<requested>-ctx<N>`
    variant (largest context wins if several are loaded). (None, None) when
    nothing matches."""
    if not requested:
        return None, None
    best: tuple[str, int | None] | None = None
    for m in ps_models:
        name = m.get("name") or m.get("model") or ""
        if name == requested:
            return name, m.get("context_length")
        if _strip_derived_suffix(name) == requested:
            ctx = m.get("context_length") or 0
            if best is None or ctx > (best[1] or 0):
                best = (name, m.get("context_length"))
    return best if best else (None, None)


_PROM_LINE_RE = re.compile(r"^([A-Za-z_:][A-Za-z0-9_:]*)(\{[^}]*\})?\s+([^\s#]+)")


def _prom_value(metrics_text: str, metric_name: str) -> float | None:
    for line in metrics_text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _PROM_LINE_RE.match(line)
        if match and match.group(1) == metric_name:
            try:
                return float(match.group(3))
            except ValueError:
                continue
    return None


def _parse_memory(metrics_text: str, os_name: str) -> tuple[int | None, int | None]:
    """Returns (total_bytes, available_bytes) from a node_exporter /metrics dump."""
    if os_name == "macos":
        total = _prom_value(metrics_text, "node_memory_total_bytes")
        free = _prom_value(metrics_text, "node_memory_free_bytes")
        inactive = _prom_value(metrics_text, "node_memory_inactive_bytes")
        purgeable = _prom_value(metrics_text, "node_memory_purgeable_bytes")
        available = None
        if free is not None and inactive is not None and purgeable is not None:
            available = free + inactive + purgeable
    else:
        total = _prom_value(metrics_text, "node_memory_MemTotal_bytes")
        available = _prom_value(metrics_text, "node_memory_MemAvailable_bytes")

    return (int(total) if total is not None else None, int(available) if available is not None else None)


def _parse_gpu(metrics_text: str, os_name: str) -> tuple[float | None, float | None, float | None]:
    """Returns (gpu_percent, gpu_temp_celsius, gpu_power_watts) from a node_exporter /metrics dump."""
    if os_name == "macos":
        percent = _prom_value(metrics_text, "mac_gpu_usage_percent")
        temp = _prom_value(metrics_text, "mac_cpu_temperature_celsius")
        power_mw = _prom_value(metrics_text, "mac_gpu_power")
        power = power_mw / 1000 if power_mw is not None else None
    else:
        ratio = _prom_value(metrics_text, "gpu_utilization_ratio")
        percent = ratio * 100 if ratio is not None else None
        temp = _prom_value(metrics_text, "gpu_temperature_celsius")
        power = _prom_value(metrics_text, "gpu_power_watts")

    return percent, temp, power


# ---------- Machines CRUD (role: machines) ----------


@router.get("/machines", response_model=list[MachineOut])
def list_machines(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    return [_to_machine_out(m) for m in db.query(OllamaMachine).order_by(OllamaMachine.id).all()]


@router.post("/machines", response_model=MachineOut, status_code=status.HTTP_201_CREATED)
def create_machine(
    payload: MachineCreate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    _check_slug_unique(db, payload.slug)
    machine = OllamaMachine(**payload.model_dump())
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
    _require_role(roles, "machines")
    machine = _get_machine_or_404(db, machine_id)

    data = payload.model_dump(exclude_unset=True)
    if data.get("slug"):
        _check_slug_unique(db, data["slug"], exclude_id=machine.id)
    for field in ("name", "slug", "ip_address", "os"):
        if data.get(field):
            setattr(machine, field, data[field])
    if data.get("api_key_read"):
        machine.api_key_read = data["api_key_read"]
    if "api_key_write" in data:
        machine.api_key_write = data["api_key_write"] or None

    db.commit()
    db.refresh(machine)
    return _to_machine_out(machine)


@router.delete("/machines/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(
    machine_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    machine = _get_machine_or_404(db, machine_id)
    db.delete(machine)
    db.commit()


# ---------- API keys CRUD (role: machines) ----------


@router.get("/keys", response_model=list[KeyOut])
def list_keys(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    return [_to_key_out(db, k) for k in db.query(OllamaKey).order_by(OllamaKey.id).all()]


@router.get("/keys/assignable-users", response_model=list[AssignableUser])
def list_assignable_users(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    users = (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.name, models.User.email)
        .all()
    )
    return [AssignableUser(id=u.id, email=u.email, name=u.name) for u in users]


# ---------- My API keys (any granted role, owner-only) ----------
#
# Declared before the /keys/{key_id} routes below: FastAPI/Starlette match
# routes by trying each registered path template in order, and `{key_id}`
# here has no `:int` converter (the int coercion happens afterwards, via the
# parameter type hint) -- so a literal segment like "mine" would otherwise
# match `/keys/{key_id}` first and fail type coercion with a 422 instead of
# ever reaching these handlers.


@router.get("/keys/mine", response_model=list[MyKeyOut])
def list_my_keys(
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    keys = db.query(OllamaKey).filter(OllamaKey.user_id == user.id).order_by(OllamaKey.id).all()
    return [_to_my_key_out(k) for k in keys]


@router.get("/keys/mine/{key_id}/reveal", response_model=KeyValueOut)
def reveal_my_key(
    key_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = _get_own_key_or_404(db, key_id, user.id)
    return KeyValueOut(value=key.value)


@router.post("/keys/mine/{key_id}/regenerate", response_model=KeyValueOut)
def regenerate_my_key(
    key_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = _get_own_key_or_404(db, key_id, user.id)
    if not key.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossibile rigenerare una chiave disattivata",
        )
    key.value = _generate_key_value()
    db.commit()
    return KeyValueOut(value=key.value)


@router.post("/keys/mine/{key_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_my_key(
    key_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = _get_own_key_or_404(db, key_id, user.id)
    if not key.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chiave già disattivata",
        )
    key.active = False
    db.commit()


@router.post("/keys", response_model=KeyDetail, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: KeyCreate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")

    machine_ids = [] if payload.all_machines else payload.machine_ids
    _validate_key_rule(payload.all_machines, machine_ids)

    key = OllamaKey(
        name=payload.name,
        value=payload.value,
        all_machines=payload.all_machines,
        active=payload.active,
        user_id=payload.user_id,
    )
    db.add(key)
    db.flush()
    _set_key_machines(db, key.id, machine_ids)
    db.commit()
    db.refresh(key)
    return _to_key_detail(db, key)


@router.get("/keys/{key_id}", response_model=KeyDetail)
def get_key(
    key_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    key = _get_key_or_404(db, key_id)
    return _to_key_detail(db, key)


@router.get("/keys/{key_id}/usage", response_model=KeyUsageOut)
def get_key_usage(
    key_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    _get_key_or_404(db, key_id)

    recent_rows = (
        db.query(OllamaKeyLog)
        .filter(OllamaKeyLog.key_id == key_id)
        .order_by(OllamaKeyLog.created_at.desc(), OllamaKeyLog.id.desc())
        .limit(10)
        .all()
    )
    recent = [
        KeyUsageEntry(created_at=r.created_at, code=r.code, response_code=r.response_code)
        for r in recent_rows
    ]

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    day_start = now - timedelta(hours=24)
    month_start = now - timedelta(days=30)

    hourly_rows = (
        db.query(OllamaKeyLog)
        .filter(OllamaKeyLog.key_id == key_id, OllamaKeyLog.created_at >= day_start)
        .all()
    )
    daily_rows = (
        db.query(OllamaKeyLog)
        .filter(OllamaKeyLog.key_id == key_id, OllamaKeyLog.created_at >= month_start)
        .all()
    )

    return KeyUsageOut(
        recent=recent,
        hourly=_bucketize(hourly_rows, day_start, 3600, 24),
        daily=_bucketize(daily_rows, month_start, 86400, 30),
    )


@router.patch("/keys/{key_id}", response_model=KeyDetail)
def update_key(
    key_id: int,
    payload: KeyUpdate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    key = _get_key_or_404(db, key_id)

    data = payload.model_dump(exclude_unset=True)
    for field in ("name", "value", "user_id"):
        if field in data:
            setattr(key, field, data[field])
    if "active" in data and data["active"] is not None:
        key.active = data["active"]
    if "all_machines" in data and data["all_machines"] is not None:
        key.all_machines = data["all_machines"]

    machine_ids = data.get("machine_ids")
    if key.all_machines:
        machine_ids = []
    elif machine_ids is None:
        machine_ids = _key_machine_ids(db, key.id)

    _validate_key_rule(key.all_machines, machine_ids)
    _set_key_machines(db, key.id, machine_ids)

    db.commit()
    db.refresh(key)
    return _to_key_detail(db, key)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(
    key_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")
    key = _get_key_or_404(db, key_id)
    db.delete(key)
    db.commit()


# ---------- Token check (public, no Blattaforma auth) ----------
#
# Called by nginx (auth_request) on every machine, once per incoming Ollama
# request, to decide whether to let it through. `Authorization` carries
# either an ollama_keys value or a machine's own api_key_read (optionally
# "Bearer <value>"), `Code` carries the machine's slug. Must only ever
# answer 204 (allowed) or 401 (denied) -- nginx's auth_request treats
# anything else as an upstream error.
#
# When the incoming Ollama request carries a model (e.g. /api/generate,
# /api/chat), nginx (njs) extracts it from the request body and forwards it
# in the `X-Ollama-Model` header -- auth_request subrequests are always GET
# and never carry a body, so the model can't be read from the body here.
# When present, the model is checked against the machine's currently loaded
# models (via /api/ps) so that a key scoped to one machine can't be used to
# probe/load a model on it out of band. The loaded model's context size is
# echoed back in the X-Ollama-Loaded-Num-Ctx response header.
#
# Every check made with an ollama_keys value (active or not) is logged to
# ollama_keys_log, with the final outcome (including the model check above,
# when applicable). Checks made with a machine's own read key are never
# logged, since that key isn't managed through ollama_keys.


@router.get("/check", status_code=status.HTTP_204_NO_CONTENT)
async def check_token(
    response: Response,
    authorization: str | None = Header(default=None),
    code: str | None = Header(default=None),
    x_ollama_model: str | None = Header(default=None),
    x_ollama_num_ctx: str | None = Header(default=None),
    x_ollama_auth_mode: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    key = db.query(OllamaKey).filter(OllamaKey.value == token).first()
    allowed = False
    own_ready_key = False

    if key and key.active:
        if key.all_machines:
            allowed = True
        else:
            match = (
                db.query(ollama_key_machine_association)
                .join(OllamaMachine, OllamaMachine.id == ollama_key_machine_association.c.machine_id)
                .filter(ollama_key_machine_association.c.key_id == key.id, OllamaMachine.slug == code)
                .first()
            )
            allowed = bool(match)

    if not allowed:
        # Fallback: a machine's own read key is always valid for that same machine (never logged).
        own_key_match = (
            db.query(OllamaMachine.id)
            .filter(OllamaMachine.api_key_read == token, OllamaMachine.slug == code)
            .first()
        )
        allowed = bool(own_key_match)
        own_ready_key = bool(own_key_match)

    detail: str | None = None

    if not own_ready_key:
        if allowed and x_ollama_auth_mode == "inference":
            loaded_context_size = None
            loaded_model_name = None
            machine = db.query(OllamaMachine).filter(OllamaMachine.slug == code).first()

            if not machine:
                allowed = False
                detail = f"Machine {code} not found"
            else:
                try:
                    async with httpx.AsyncClient(timeout=AUTH_CHECK_TIMEOUT) as client:
                        resp = await client.get(
                            f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/ps",
                            headers=_auth_header(machine.api_key_read),
                        )
                        resp.raise_for_status()
                        ps_data = resp.json()
                    loaded_model_name, loaded_context_size = _match_loaded_model(
                        ps_data.get("models", []), x_ollama_model
                    )
                except httpx.HTTPError:
                    pass

            if loaded_context_size is None:
                allowed = False
                detail = f"Model {x_ollama_model} not loaded on machine"
            elif x_ollama_num_ctx is not None and int(x_ollama_num_ctx) > loaded_context_size:
                allowed = False
                detail = f"Requested context size {x_ollama_num_ctx} exceeds loaded model's context size {loaded_context_size}"
            else:
                response.headers["X-Ollama-Loaded-Num-Ctx"] = str(loaded_context_size)
                # Tell nginx (njs) which loaded variant to route the request to,
                # so a request naming the base model reuses the already-loaded
                # derived model instead of triggering a reload.
                if loaded_model_name and loaded_model_name != x_ollama_model:
                    response.headers["X-Ollama-Loaded-Model"] = loaded_model_name

    # Log reflects the final outcome (including the model/context check above),
    # not just the initial key/machine authorization.
    if key is not None:
        response_code = status.HTTP_204_NO_CONTENT if allowed else status.HTTP_401_UNAUTHORIZED
        db.add(OllamaKeyLog(key_id=key.id, code=code, response_code=response_code))
        db.commit()

    if not allowed:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


# ---------- Status (any granted role) ----------


@router.get("/machines/{machine_id}/status", response_model=MachineStatusOut)
async def machine_status(
    machine_id: int,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    machine = _get_machine_or_404(db, machine_id)
    out = MachineStatusOut(
        id=machine.id,
        name=machine.name,
        slug=machine.slug,
        ip_address=machine.ip_address,
        os=machine.os,
        has_write_key=bool(machine.api_key_write),
    )
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=STATUS_TIMEOUT) as client:
        try:
            resp = await client.get(f"http://{machine.ip_address}:{NODE_EXPORTER_PORT}/metrics")
            resp.raise_for_status()
            out.total_bytes, out.available_bytes = _parse_memory(resp.text, machine.os)
            out.gpu_percent, out.gpu_temp_celsius, out.gpu_power_watts = _parse_gpu(resp.text, machine.os)
        except Exception:
            errors.append("node_exporter non raggiungibile")

        try:
            resp = await client.get(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/ps",
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
            data = resp.json()
            out.loaded_models = [
                ModelInfo(
                    name=m.get("name") or m.get("model"),
                    size_bytes=m.get("size") or 0,
                    context_size=m.get("context_length"),
                )
                for m in data.get("models", [])
            ]
            out.ollama_bytes = sum(m.size_bytes for m in out.loaded_models)
        except Exception:
            errors.append("Ollama (ps) non raggiungibile")

        try:
            resp = await client.get(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/tags",
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
            data = resp.json()
            out.available_models = [
                ModelInfo(name=m.get("name") or m.get("model"), size_bytes=m.get("size") or 0)
                for m in data.get("models", [])
                if not _is_derived_model(m.get("name") or m.get("model") or "")
            ]
        except Exception:
            errors.append("Ollama (list) non raggiungibile")

    _annotate_pinned(db, machine.id, out.loaded_models)

    if errors:
        out.error = "; ".join(errors)
    return out


def _annotate_pinned(db: Session, machine_id: int, loaded_models: list[ModelInfo]) -> None:
    """Marca i modelli caricati che risultano bloccati in RAM."""
    if not loaded_models:
        return
    pins = {
        p.model: p
        for p in db.query(OllamaPinnedModel)
        .filter(
            OllamaPinnedModel.machine_id == machine_id,
            OllamaPinnedModel.ended_at.is_(None),
        )
        .all()
    }
    if not pins:
        return
    user_ids = {p.pinned_by_user_id for p in pins.values() if p.pinned_by_user_id}
    emails = (
        {u.id: u.email for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    for mi in loaded_models:
        pin = pins.get(mi.name)
        if pin is not None:
            mi.pinned = True
            mi.pinned_by_email = emails.get(pin.pinned_by_user_id)


# ---------- Load a model into RAM (any granted role) ----------


@router.post("/machines/{machine_id}/load")
async def load_model(
    machine_id: int,
    payload: LoadModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    machine = _get_machine_or_404(db, machine_id)
    derived = _derived_model_name(payload.model, payload.context_size)
    try:
        async with httpx.AsyncClient(timeout=LOAD_MODEL_TIMEOUT) as client:
            # Always (re)create a derived model with num_ctx baked into its
            # Modelfile. It's a tiny manifest that shares the base's weight
            # blobs; recreating it costs next to nothing and re-aligns it if the
            # base model was pulled anew. This is what makes the context stick
            # on the OpenAI-compatible endpoint, which has no num_ctx parameter.
            resp = await client.post(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/create",
                json={
                    "model": derived,
                    "from": payload.model,
                    "parameters": {"num_ctx": payload.context_size},
                    "stream": False,
                },
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
            # Load the derived model into RAM (num_ctx comes from its Modelfile).
            # Se il modello è già bloccato, mantieni il keep_alive=-1: un load
            # senza keep_alive lo riporterebbe al timeout di default.
            generate_body = {
                "model": derived,
                "stream": False,
                "options": {"num_ctx": payload.context_size},
            }
            if _active_pin(db, machine.id, derived) is not None:
                generate_body["keep_alive"] = -1
            resp = await client.post(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
                json=generate_body,
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Impossibile caricare il modello: {exc}"
        ) from exc
    return {"status": "ok"}


# ---------- Unload a model from RAM ----------
#
# Chiunque abbia un ruolo del modulo può espellere un modello NON bloccato
# (gli utenti senza privilegio "models" restano soggetti alla finestra minima).
# Un modello bloccato può essere espulso solo da un admin o da un utente con
# privilegio "models"; l'espulsione chiude anche il blocco.


@router.post("/machines/{machine_id}/unload")
async def unload_model(
    machine_id: int,
    payload: LoadModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    machine = _get_machine_or_404(db, machine_id)
    pin = _active_pin(db, machine.id, payload.model)

    if pin is not None and "models" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un amministratore o un utente con privilegio 'models' può espellere un modello bloccato",
        )

    try:
        async with httpx.AsyncClient(timeout=UNLOAD_MODEL_TIMEOUT) as client:
            resp = await client.get(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/ps",
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
            ps_data = resp.json()

            model_entry = next(
                (m for m in ps_data.get("models", []) if (m.get("name") or m.get("model")) == payload.model),
                None,
            )
            if model_entry is None:
                # Non caricato: niente da espellere, ma chiudiamo un eventuale
                # blocco pendente così il refresh smette di ricaricarlo.
                if pin is not None:
                    pin.ended_at = _utcnow()
                    db.commit()
                return {"status": "ok"}

            # La finestra minima si applica solo ai modelli non bloccati e agli
            # utenti senza privilegio "models".
            if pin is None:
                expires_at = model_entry.get("expires_at")
                if expires_at and "models" not in roles:
                    until_minutes = (datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)).total_seconds() / 60
                    if until_minutes >= settings.ollama_max_minutes:
                        remaining = math.ceil(until_minutes - settings.ollama_max_minutes)
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Il modello può essere smontato solo tra {remaining} minuti",
                        )

            resp = await client.post(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
                json={"model": payload.model, "keep_alive": 0, "stream": False},
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Impossibile espellere il modello: {exc}"
        ) from exc

    if pin is not None:
        pin.ended_at = _utcnow()
        db.commit()
    return {"status": "ok"}


# ---------- Pin / unpin a model in RAM (role: models) ----------


@router.post("/machines/{machine_id}/pin")
async def pin_model(
    machine_id: int,
    payload: PinModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_role(roles, "models")
    machine = _get_machine_or_404(db, machine_id)

    if _active_pin(db, machine.id, payload.model) is not None:
        return {"status": "ok"}

    try:
        async with httpx.AsyncClient(timeout=UNLOAD_MODEL_TIMEOUT) as client:
            resp = await client.get(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/ps",
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
            entry = next(
                (
                    m
                    for m in resp.json().get("models", [])
                    if (m.get("name") or m.get("model")) == payload.model
                ),
                None,
            )
            if entry is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Il modello non è caricato in RAM",
                )
            context_size = (
                entry.get("context_length")
                or _derived_context_size(payload.model)
                or LoadModelRequest.model_fields["context_size"].default
            )
            resp = await client.post(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
                json={"model": payload.model, "keep_alive": -1, "stream": False},
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Impossibile bloccare il modello: {exc}"
        ) from exc

    db.add(
        OllamaPinnedModel(
            machine_id=machine.id,
            model=payload.model,
            context_size=int(context_size),
            pinned_by_user_id=user.id,
            started_at=_utcnow(),
        )
    )
    db.commit()
    return {"status": "ok"}


@router.post("/machines/{machine_id}/unpin")
async def unpin_model(
    machine_id: int,
    payload: PinModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "models")
    machine = _get_machine_or_404(db, machine_id)

    pin = _active_pin(db, machine.id, payload.model)
    if pin is None:
        return {"status": "ok"}

    pin.ended_at = _utcnow()
    db.commit()

    # Il modello resta in RAM ma torna a scadere con il keep_alive di default
    # della macchina: una generate senza keep_alive resetta il timer.
    try:
        async with httpx.AsyncClient(timeout=UNLOAD_MODEL_TIMEOUT) as client:
            resp = await client.post(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
                json={"model": payload.model, "stream": False},
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning(
            "Ollama: sblocco di %s su %s riuscito, ma il reset del keep_alive di default è fallito",
            payload.model,
            machine.slug,
        )
    return {"status": "ok"}


# ---------- Pull a new model (role: models) ----------


@router.post("/machines/{machine_id}/pull")
async def pull_model(
    machine_id: int,
    payload: PullModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "models")
    machine = _get_machine_or_404(db, machine_id)

    api_key_write = machine.api_key_write

    if not api_key_write:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Questa macchina non ha una chiave API in scrittura configurata",
        )

    async def event_stream():
        async with httpx.AsyncClient(timeout=PULL_MODEL_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"http://{machine.ip_address}:{OLLAMA_WRITE_PORT}/api/pull",
                json={"model": payload.model, "stream": True},
                headers=_auth_header(api_key_write),
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        yield line + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ---------- Refresh periodico dei modelli bloccati ----------
#
# Ogni chiamata a Ollama senza `keep_alive` riporta il modello al timeout di
# default della macchina, quindi un modello "bloccato" (caricato con
# keep_alive=-1) va rinfrescato periodicamente. Un thread daemon, avviato una
# volta per processo, si occupa del refresh; poiché il backend gira con più
# worker uvicorn, i thread si contendono un file lock e solo quello che lo
# ottiene esegue davvero il refresh (gli altri riprovano finché il leader non
# muore). All'avvio il primo giro ricarica i modelli che risultavano bloccati
# prima di un eventuale riavvio della Blattaforma.

_SCHEDULER_LOCK_PATH = settings.ollama_pin_scheduler_lock_path or str(
    BASE_DIR / "ollama_pin_scheduler.lock"
)
_scheduler_lock_fh = None
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _acquire_scheduler_lock():
    """Prova ad acquisire il file lock non bloccante. Ritorna l'handle del file
    (da tenere vivo per tutta la durata del processo) o None se un altro worker
    lo detiene già."""
    global _scheduler_lock_fh
    fh = open(_SCHEDULER_LOCK_PATH, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    _scheduler_lock_fh = fh
    return fh


def _refresh_interval_seconds() -> int:
    return max(60, settings.ollama_pin_refresh_minutes * 60)


def _pin_scheduler_loop() -> None:
    # Aspetta il file lock: se un altro worker lo detiene, riprova ogni minuto
    # così da subentrare se il leader dovesse terminare.
    while _acquire_scheduler_lock() is None:
        time.sleep(60)

    logger.info("Ollama: scheduler dei modelli bloccati avviato (refresh ogni %d min)", settings.ollama_pin_refresh_minutes)
    time.sleep(10)  # lascia stabilizzare l'avvio
    while True:
        try:
            _refresh_pinned_models()
        except Exception:
            logger.exception("Ollama: refresh dei modelli bloccati fallito")
        time.sleep(_refresh_interval_seconds())


def _refresh_pinned_models() -> None:
    db = SessionLocal()
    try:
        pins = (
            db.query(OllamaPinnedModel)
            .filter(OllamaPinnedModel.ended_at.is_(None))
            .all()
        )
        if not pins:
            return
        machines = {m.id: m for m in db.query(OllamaMachine).all()}
        by_machine: dict[int, list[OllamaPinnedModel]] = {}
        for pin in pins:
            by_machine.setdefault(pin.machine_id, []).append(pin)

        with httpx.Client(timeout=LOAD_MODEL_TIMEOUT) as client:
            for machine_id, machine_pins in by_machine.items():
                machine = machines.get(machine_id)
                if machine is None:
                    continue
                try:
                    _refresh_machine_pins(client, machine, machine_pins)
                except Exception:
                    logger.exception(
                        "Ollama: refresh dei modelli bloccati fallito per la macchina %s", machine.slug
                    )
    finally:
        db.close()


def _refresh_machine_pins(client: httpx.Client, machine: OllamaMachine, pins: list[OllamaPinnedModel]) -> None:
    resp = client.get(
        f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/ps",
        headers=_auth_header(machine.api_key_read),
    )
    resp.raise_for_status()
    loaded = {(m.get("name") or m.get("model")) for m in resp.json().get("models", [])}

    for pin in pins:
        try:
            if pin.model in loaded:
                resp = client.post(
                    f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
                    json={"model": pin.model, "keep_alive": -1, "stream": False},
                    headers=_auth_header(machine.api_key_read),
                )
                resp.raise_for_status()
            else:
                _reload_pinned_model(client, machine, pin)
        except Exception:
            logger.exception(
                "Ollama: impossibile rinfrescare il modello bloccato %s su %s", pin.model, machine.slug
            )


def _reload_pinned_model(client: httpx.Client, machine: OllamaMachine, pin: OllamaPinnedModel) -> None:
    """Ricarica un modello bloccato caduto dalla RAM, replicando il flusso di
    /load: (ri)crea la variante derivata con num_ctx nel Modelfile, poi la
    carica con keep_alive=-1."""
    base_model = _strip_derived_suffix(pin.model)
    if base_model != pin.model:
        # Ricrea la variante derivata (manifest leggero, condivide i blob dei
        # pesi) così num_ctx resta valido anche sull'endpoint OpenAI.
        resp = client.post(
            f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/create",
            json={
                "model": pin.model,
                "from": base_model,
                "parameters": {"num_ctx": pin.context_size},
                "stream": False,
            },
            headers=_auth_header(machine.api_key_read),
        )
        resp.raise_for_status()
    resp = client.post(
        f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
        json={
            "model": pin.model,
            "keep_alive": -1,
            "stream": False,
            "options": {"num_ctx": pin.context_size},
        },
        headers=_auth_header(machine.api_key_read),
    )
    resp.raise_for_status()
    logger.info("Ollama: modello bloccato %s ricaricato su %s", pin.model, machine.slug)


def _start_pin_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=_pin_scheduler_loop, name="ollama-pin-scheduler", daemon=True).start()


Base.metadata.create_all(bind=engine)
_start_pin_scheduler()
