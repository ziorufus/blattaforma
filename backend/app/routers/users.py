from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models
from ..deps import get_db, require_admin
from ..schemas import (
    ModulePermissionGrant,
    PermissionsUpdate,
    UserCreate,
    UserDetailOut,
    UserGroupsUpdate,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _to_user_out(user: models.User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        group_ids=[g.id for g in user.groups],
    )


def _to_user_detail(user: models.User, db: Session) -> UserDetailOut:
    from ..schemas import GroupOut

    return UserDetailOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        group_ids=[g.id for g in user.groups],
        groups=[
            GroupOut(
                id=g.id,
                name=g.name,
                description=g.description,
                created_at=g.created_at,
                member_count=len(g.users),
            )
            for g in user.groups
        ],
        permissions=[
            ModulePermissionGrant(module_name=p.module.name, role=p.role)
            for p in user.module_permissions
        ],
        effective_permissions=crud.effective_permissions(db, user),
    )


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return [_to_user_out(u) for u in db.query(models.User).order_by(models.User.id).all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    user = models.User(email=payload.email, name=payload.name, is_admin=payload.is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.get("/{user_id}", response_model=UserDetailOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user_detail(user, db)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin privileges")
    if user.id == current_admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    if payload.name is not None:
        user.name = payload.name
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()


@router.put("/{user_id}/groups", response_model=UserDetailOut)
def set_user_groups(user_id: int, payload: UserGroupsUpdate, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    groups = db.query(models.Group).filter(models.Group.id.in_(payload.group_ids)).all()
    if len(groups) != len(set(payload.group_ids)):
        raise HTTPException(status_code=400, detail="One or more group ids do not exist")
    user.groups = groups
    db.commit()
    db.refresh(user)
    return _to_user_detail(user, db)


@router.put("/{user_id}/permissions", response_model=UserDetailOut)
def set_user_permissions(user_id: int, payload: PermissionsUpdate, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    module_cache: dict[str, models.Module] = {}
    for grant in payload.permissions:
        if grant.module_name not in module_cache:
            module = crud.get_module_by_name(db, grant.module_name)
            if not module:
                raise HTTPException(status_code=400, detail=f"Unknown module '{grant.module_name}'")
            module_cache[grant.module_name] = module
        module = module_cache[grant.module_name]
        if grant.role not in module.roles:
            raise HTTPException(
                status_code=400,
                detail=f"Role '{grant.role}' is not valid for module '{grant.module_name}'",
            )

    db.query(models.UserModulePermission).filter(
        models.UserModulePermission.user_id == user.id
    ).delete()
    for grant in payload.permissions:
        module = module_cache[grant.module_name]
        db.add(models.UserModulePermission(user_id=user.id, module_id=module.id, role=grant.role))

    db.commit()
    db.refresh(user)
    return _to_user_detail(user, db)
