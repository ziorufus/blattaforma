"""Discovers self-contained feature modules dropped into app/modules/ and:
  1. mounts their FastAPI router under /api/modules/{module_name}
  2. upserts a row describing them into the `modules` DB table

A module is a single .py file in this package that defines:
  MODULE_NAME  -- unique slug (letters, numbers, - and _), also the URL/API prefix
  MODULE_LABEL -- human readable name shown in the frontend menu
  MODULE_ROLES -- list of role strings available for this module
  router       -- a fastapi.APIRouter with the module's endpoints

Optionally:
  MODULE_OPTIONS -- a pydantic.BaseModel subclass declaring the module's
                    admin-editable options (see app/options.py)

Every route of a module disabled from the admin options page answers 404.
"""

import importlib
import logging
import pkgutil
import re

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models, options
from .database import SessionLocal
from .deps import require_module_enabled

logger = logging.getLogger("blattaforma.modules")

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def discover_modules() -> list[dict]:
    """Import every module under app.modules and return their manifests."""
    import app.modules as modules_pkg

    manifests = []
    for _, module_name, is_pkg in pkgutil.iter_modules(modules_pkg.__path__):
        if is_pkg or module_name.startswith("_"):
            continue

        mod = importlib.import_module(f"app.modules.{module_name}")

        name = getattr(mod, "MODULE_NAME", None)
        label = getattr(mod, "MODULE_LABEL", None)
        roles = getattr(mod, "MODULE_ROLES", None)
        router = getattr(mod, "router", None)
        module_options = getattr(mod, "MODULE_OPTIONS", None)

        if not name or not label or roles is None or router is None:
            logger.warning(
                "Skipping module file '%s.py': missing MODULE_NAME/MODULE_LABEL/MODULE_ROLES/router",
                module_name,
            )
            continue

        if not NAME_RE.match(name):
            logger.warning(
                "Skipping module '%s': MODULE_NAME must match %s", name, NAME_RE.pattern
            )
            continue

        if name == options.GLOBAL_SCOPE:
            logger.warning("Skipping module '%s': name reserved for global options", name)
            continue

        if module_options is not None and not (
            isinstance(module_options, type) and issubclass(module_options, BaseModel)
        ):
            logger.warning("Module '%s': MODULE_OPTIONS is not a pydantic model, ignored", name)
            module_options = None

        manifests.append(
            {
                "name": name,
                "label": label,
                "roles": list(roles),
                "router": router,
                "options": module_options,
            }
        )

    return manifests


def sync_modules_to_db(manifests: list[dict]) -> None:
    db: Session = SessionLocal()
    try:
        for manifest in manifests:
            existing = db.query(models.Module).filter(models.Module.name == manifest["name"]).first()
            if existing is None:
                db.add(
                    models.Module(
                        name=manifest["name"], label=manifest["label"], roles=manifest["roles"]
                    )
                )
                logger.info("Discovered new module '%s'", manifest["name"])
            else:
                existing.label = manifest["label"]
                existing.roles = manifest["roles"]
        db.commit()
    finally:
        db.close()


def load_modules(app: FastAPI) -> None:
    manifests = discover_modules()

    seen_names = set()
    for manifest in manifests:
        if manifest["name"] in seen_names:
            logger.warning("Duplicate module name '%s' skipped", manifest["name"])
            continue
        seen_names.add(manifest["name"])

        app.include_router(
            manifest["router"],
            prefix=f"/api/modules/{manifest['name']}",
            tags=[f"module:{manifest['name']}"],
            dependencies=[Depends(require_module_enabled(manifest["name"]))],
        )
        if manifest["options"] is not None:
            options.register_scope(manifest["name"], manifest["options"])

    sync_modules_to_db(manifests)
    logger.info("Loaded %d module(s): %s", len(seen_names), ", ".join(sorted(seen_names)) or "-")
