"""Opzioni configurabili dagli admin, globali o per singolo modulo.

Lo schema di ogni gruppo di opzioni (scope) è un modello Pydantic dichiarato
in codice: tipo, default, etichetta (`title`), descrizione e vincoli stanno
lì. Nella tabella `options` finiscono solo i valori modificati da un admin;
un'opzione senza riga vale il default del codice, quindi cambiare un default
nel codice si propaga a chi non l'ha mai toccato.

Scope: `global` per le opzioni della piattaforma, `MODULE_NAME` per quelle di
un modulo (che le dichiara esportando `MODULE_OPTIONS`, vedi module_loader).

Un'opzione è leggibile senza login solo se dichiarata con
`Field(..., json_schema_extra={"public": True})`.

Nessuna cache: il backend gira con più worker uvicorn e una cache in memoria
resterebbe disallineata dopo una modifica fatta da un altro worker. Le
letture su SQLite costano poco, quindi si legge sempre dal DB.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal

logger = logging.getLogger("blattaforma.options")

GLOBAL_SCOPE = "global"


class GlobalOptions(BaseModel):
    google_auth_enabled: bool = Field(
        True,
        title="Accesso con Google",
        description="Mostra il pulsante di login con Google. Richiede GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET in .env.",
        json_schema_extra={"public": True},
    )
    microsoft_auth_enabled: bool = Field(
        True,
        title="Accesso con Microsoft",
        description="Mostra il pulsante di login con Microsoft. Richiede MICROSOFT_CLIENT_ID e MICROSOFT_CLIENT_SECRET in .env.",
        json_schema_extra={"public": True},
    )


_schemas: dict[str, type[BaseModel]] = {GLOBAL_SCOPE: GlobalOptions}


class UnknownOptionError(KeyError):
    pass


def register_scope(scope: str, schema: type[BaseModel]) -> None:
    _schemas[scope] = schema


def get_schema(scope: str) -> type[BaseModel] | None:
    return _schemas.get(scope)


def registered_scopes() -> list[str]:
    return list(_schemas)


def is_public(schema: type[BaseModel], key: str) -> bool:
    extra = schema.model_fields[key].json_schema_extra
    return isinstance(extra, dict) and bool(extra.get("public"))


def _stored_rows(db: Session, scope: str) -> dict[str, models.Option]:
    rows = db.query(models.Option).filter(models.Option.scope == scope).all()
    return {r.key: r for r in rows}


def _resolve(schema: type[BaseModel], scope: str, stored: dict[str, Any]) -> BaseModel:
    """Combina i valori salvati con i default. Un valore salvato non più valido
    (es. tipo o vincoli cambiati nel codice) viene scartato a favore del
    default, invece di rendere inutilizzabile l'intero scope."""
    values = {k: v for k, v in stored.items() if k in schema.model_fields}
    try:
        return schema.model_validate(values)
    except ValidationError as exc:
        bad = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
        logger.warning("Opzioni '%s': valori salvati non validi ignorati: %s", scope, ", ".join(sorted(bad)))
        return schema.model_validate({k: v for k, v in values.items() if k not in bad})


def get_options(db: Session, scope: str) -> BaseModel:
    """Valori correnti (salvati o di default) di uno scope, come istanza del
    suo modello Pydantic: `get_options(db, "ollama").max_minutes`."""
    schema = _schemas.get(scope)
    if schema is None:
        raise UnknownOptionError(scope)
    stored = {k: r.value for k, r in _stored_rows(db, scope).items()}
    return _resolve(schema, scope, stored)


def read_options(scope: str) -> BaseModel:
    """Come get_options, ma apre una sessione propria: per thread in
    background che non hanno una sessione della richiesta."""
    db = SessionLocal()
    try:
        return get_options(db, scope)
    finally:
        db.close()


def set_option(db: Session, scope: str, key: str, value: Any, user: models.User | None) -> Any:
    """Valida e salva un valore. Solleva UnknownOptionError o ValidationError."""
    schema = _schemas.get(scope)
    if schema is None or key not in schema.model_fields:
        raise UnknownOptionError(f"{scope}.{key}")

    current = get_options(db, scope).model_dump()
    current[key] = value
    stored_value = schema.model_validate(current).model_dump(mode="json")[key]

    row = db.get(models.Option, (scope, key))
    if row is None:
        row = models.Option(scope=scope, key=key)
        db.add(row)
    row.value = stored_value
    row.updated_by_id = user.id if user else None
    db.commit()
    return stored_value


def reset_option(db: Session, scope: str, key: str) -> None:
    schema = _schemas.get(scope)
    if schema is None or key not in schema.model_fields:
        raise UnknownOptionError(f"{scope}.{key}")
    row = db.get(models.Option, (scope, key))
    if row is not None:
        db.delete(row)
        db.commit()


def describe_scope(db: Session, scope: str) -> list[dict]:
    """Elenco delle opzioni di uno scope per la pagina di amministrazione:
    valore corrente, default, JSON Schema del campo (da cui il frontend
    genera il controllo del form) e chi l'ha modificata per ultimo."""
    schema = _schemas[scope]
    rows = _stored_rows(db, scope)
    current = _resolve(schema, scope, {k: r.value for k, r in rows.items()}).model_dump(mode="json")
    defaults = schema().model_dump(mode="json")
    properties = schema.model_json_schema().get("properties", {})

    items = []
    for key, field in schema.model_fields.items():
        row = rows.get(key)
        items.append(
            {
                "key": key,
                "label": field.title or key,
                "description": field.description,
                "json_schema": properties.get(key, {}),
                "public": is_public(schema, key),
                "default": defaults[key],
                "value": current[key],
                "is_default": row is None,
                "updated_at": row.updated_at if row else None,
                "updated_by": row.updated_by.email if row and row.updated_by else None,
            }
        )
    return items


def public_options(db: Session) -> dict[str, dict[str, Any]]:
    """Solo le opzioni marcate come pubbliche, raggruppate per scope. Gli
    scope dei moduli disattivati sono esclusi."""
    disabled = {
        m.name for m in db.query(models.Module).filter(models.Module.enabled.is_(False)).all()
    }
    result: dict[str, dict[str, Any]] = {}
    for scope, schema in _schemas.items():
        if scope in disabled:
            continue
        public_keys = [k for k in schema.model_fields if is_public(schema, k)]
        if not public_keys:
            continue
        values = get_options(db, scope).model_dump(mode="json")
        result[scope] = {k: values[k] for k in public_keys}
    return result


def is_module_enabled(db: Session, module_name: str) -> bool:
    module = db.query(models.Module).filter(models.Module.name == module_name).first()
    return module is not None and module.enabled


def module_enabled(module_name: str) -> bool:
    """Come is_module_enabled, con una sessione propria (per gli scheduler)."""
    db = SessionLocal()
    try:
        return is_module_enabled(db, module_name)
    finally:
        db.close()
