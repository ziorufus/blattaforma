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
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..database import Base, engine
from ..deps import get_db, require_module_role

MODULE_NAME = "ollama"
MODULE_LABEL = "Ollama"
MODULE_ROLES = ["machines", "models", "standard"]

OLLAMA_READ_PORT = 11435
OLLAMA_WRITE_PORT = 11436
NODE_EXPORTER_PORT = 9100

router = APIRouter()


# ---------- DB model ----------


class OllamaMachine(Base):
    __tablename__ = "ollama_machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_read: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_write: Mapped[str] = mapped_column(String(512), nullable=True)
    os: Mapped[str] = mapped_column(String(20), nullable=False)


# ---------- Schemas ----------


class MachineCreate(BaseModel):
    name: str
    ip_address: str
    api_key_read: str
    api_key_write: str | None = None
    os: Literal["macos", "linux"]


class MachineUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = None
    api_key_read: str | None = None
    api_key_write: str | None = None
    os: Literal["macos", "linux"] | None = None


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip_address: str
    os: str
    has_write_key: bool


class ModelInfo(BaseModel):
    name: str
    size_bytes: int


class MachineStatusOut(BaseModel):
    id: int
    name: str
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


class PullModelRequest(BaseModel):
    model: str


# ---------- Helpers ----------


def _to_machine_out(machine: OllamaMachine) -> MachineOut:
    return MachineOut(
        id=machine.id,
        name=machine.name,
        ip_address=machine.ip_address,
        os=machine.os,
        has_write_key=bool(machine.api_key_write),
    )


def _get_machine_or_404(db: Session, machine_id: int) -> OllamaMachine:
    machine = db.query(OllamaMachine).filter(OllamaMachine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Macchina non trovata")
    return machine


def _require_role(roles: list[str], role: str) -> None:
    if role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Richiesto il ruolo '{role}'")


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
    for field in ("name", "ip_address", "os"):
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
                ModelInfo(name=m.get("name") or m.get("model"), size_bytes=m.get("size") or 0)
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
                json={"model": payload.model, "stream": False},
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
