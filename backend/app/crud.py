from sqlalchemy.orm import Session

from . import models


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_module_by_name(db: Session, name: str) -> models.Module | None:
    return db.query(models.Module).filter(models.Module.name == name).first()


def effective_permissions(db: Session, user: models.User) -> dict[str, list[str]]:
    """Return {module_name: [roles]} granted to the user, merging direct
    grants with grants inherited from the user's groups. If the user is an
    admin, every discovered module's full role list is returned."""
    if user.is_admin:
        modules = db.query(models.Module).all()
        return {m.name: list(m.roles) for m in modules}

    result: dict[str, set[str]] = {}

    for perm in user.module_permissions:
        result.setdefault(perm.module.name, set()).add(perm.role)

    for group in user.groups:
        for perm in group.module_permissions:
            result.setdefault(perm.module.name, set()).add(perm.role)

    return {name: sorted(roles) for name, roles in result.items()}


def user_roles_for_module(db: Session, user: models.User, module_name: str) -> list[str]:
    return effective_permissions(db, user).get(module_name, [])
