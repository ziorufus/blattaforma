from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from . import crud, models
from .auth import decode_access_token
from .database import get_db

__all__ = ["get_db", "get_current_user", "require_admin", "require_module_role"]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth_header.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = crud.get_user(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


def require_module_role(module_name: str):
    """Dependency factory used by feature modules to guard their endpoints.
    Returns the caller's granted roles for the module (never empty)."""

    def dependency(
        user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> list[str]:
        if user.is_admin:
            module = crud.get_module_by_name(db, module_name)
            return list(module.roles) if module else []

        roles = crud.user_roles_for_module(db, user, module_name)
        if not roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this module")
        return roles

    return dependency
