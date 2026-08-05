"""Ollama module: manages a fleet of machines running Ollama and lets
enabled users inspect loaded models / RAM usage, load an already-downloaded
model into RAM, and (for machines with a write key) pull new models.

Machine API keys are stored server-side only and never serialized back to
the frontend: every call to a machine's Ollama instance is proxied through
this router, which attaches the key as an `Authorization: Bearer ...` header.
"""

import re
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..database import Base, engine
from ..deps import get_db, require_module_role

MODULE_NAME = "ollama"
MODULE_LABEL = "Ollama"
MODULE_ROLES = ["machines", "models", "standard"]

OLLAMA_READ_PORT = 11435
OLLAMA_WRITE_PORT = 11436
NODE_EXPORTER_PORT = 9100

SLUG_PATTERN = r"^[a-z0-9-]+$"

router = APIRouter()


# ---------- DB model ----------


class OllamaMachine(Base):
    __tablename__ = "ollama_machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_read: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_write: Mapped[str] = mapped_column(String(512), nullable=True)
    os: Mapped[str] = mapped_column(String(20), nullable=False)


class OllamaKey(Base):
    __tablename__ = "ollama_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=True)
    all_machines: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


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
    label: str | None = None
    all_machines: bool = False
    active: bool = True
    machine_ids: list[int] = []


class KeyUpdate(BaseModel):
    name: str | None = None
    value: str | None = None
    label: str | None = None
    all_machines: bool | None = None
    active: bool | None = None
    machine_ids: list[int] | None = None


class KeyOut(BaseModel):
    id: int
    name: str
    masked_value: str
    label: str | None
    all_machines: bool
    active: bool
    machine_ids: list[int]
    machine_names: list[str]


class KeyDetail(BaseModel):
    id: int
    name: str
    value: str
    label: str | None
    all_machines: bool
    active: bool
    machine_ids: list[int]
    machine_names: list[str]


class ModelInfo(BaseModel):
    name: str
    size_bytes: int
    context_size: int | None = None


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


def _validate_key_rule(all_machines: bool, machine_ids: list[int], label: str | None) -> None:
    if not all_machines and not machine_ids and not (label and label.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Specificare almeno una tra: tutte le macchine, una macchina associata o un'etichetta",
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
        label=key.label,
        all_machines=key.all_machines,
        active=key.active,
        machine_ids=machine_ids,
        machine_names=machine_names,
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
        label=key.label,
        all_machines=key.all_machines,
        active=key.active,
        machine_ids=machine_ids,
        machine_names=machine_names,
    )


def _auth_header(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


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


@router.post("/keys", response_model=KeyDetail, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: KeyCreate,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    _require_role(roles, "machines")

    machine_ids = [] if payload.all_machines else payload.machine_ids
    _validate_key_rule(payload.all_machines, machine_ids, payload.label)

    key = OllamaKey(
        name=payload.name,
        value=payload.value,
        label=payload.label,
        all_machines=payload.all_machines,
        active=payload.active,
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
    for field in ("name", "value", "label"):
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

    _validate_key_rule(key.all_machines, machine_ids, key.label)
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
            machine = db.query(OllamaMachine).filter(OllamaMachine.slug == code).first()

            if not machine:
                allowed = False
                detail = f"Machine {code} not found"
            else:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(
                            f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/ps",
                            headers=_auth_header(machine.api_key_read),
                        )
                        resp.raise_for_status()
                        ps_data = resp.json()
                    for m in ps_data.get("models", []):
                        if (m.get("name") or m.get("model")) == x_ollama_model:
                            loaded_context_size = m.get("context_length")
                            break
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

    async with httpx.AsyncClient(timeout=5.0) as client:
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
            ]
        except Exception:
            errors.append("Ollama (list) non raggiungibile")

    if errors:
        out.error = "; ".join(errors)
    return out


# ---------- Load a model into RAM (any granted role) ----------


@router.post("/machines/{machine_id}/load")
async def load_model(
    machine_id: int,
    payload: LoadModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    machine = _get_machine_or_404(db, machine_id)
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"http://{machine.ip_address}:{OLLAMA_READ_PORT}/api/generate",
                json={
                    "model": payload.model,
                    "stream": False,
                    "options": {"num_ctx": payload.context_size},
                },
                headers=_auth_header(machine.api_key_read),
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Impossibile caricare il modello: {exc}"
        ) from exc
    return {"status": "ok"}


# ---------- Unload a model from RAM (any granted role) ----------


@router.post("/machines/{machine_id}/unload")
async def unload_model(
    machine_id: int,
    payload: LoadModelRequest,
    roles: list[str] = Depends(require_module_role(MODULE_NAME)),
    db: Session = Depends(get_db),
):
    machine = _get_machine_or_404(db, machine_id)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
    if not machine.api_key_write:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Questa macchina non ha una chiave API in scrittura configurata",
        )

    async def event_stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"http://{machine.ip_address}:{OLLAMA_WRITE_PORT}/api/pull",
                json={"model": payload.model, "stream": True},
                headers=_auth_header(machine.api_key_write),
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        yield line + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


Base.metadata.create_all(bind=engine)
