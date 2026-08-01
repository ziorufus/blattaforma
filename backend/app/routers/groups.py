from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models
from ..deps import get_db, require_admin
from ..schemas import (
    GroupCreate,
    GroupDetailOut,
    GroupOut,
    GroupMembersUpdate,
    GroupUpdate,
    ModulePermissionGrant,
    PermissionsUpdate,
    UserSummary,
)

router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(require_admin)])


def _to_group_out(group: models.Group) -> GroupOut:
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        member_count=len(group.users),
    )


def _to_group_detail(group: models.Group) -> GroupDetailOut:
    return GroupDetailOut(
        id=group.id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        member_count=len(group.users),
        members=[UserSummary.model_validate(u) for u in group.users],
        permissions=[
            ModulePermissionGrant(module_name=p.module.name, role=p.role)
            for p in group.module_permissions
        ],
    )


def _get_group_or_404(db: Session, group_id: int) -> models.Group:
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.get("", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return [_to_group_out(g) for g in db.query(models.Group).order_by(models.Group.id).all()]


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: Session = Depends(get_db)):
    if db.query(models.Group).filter(models.Group.name == payload.name).first():
        raise HTTPException(status_code=400, detail="A group with this name already exists")
    group = models.Group(name=payload.name, description=payload.description)
    db.add(group)
    db.commit()
    db.refresh(group)
    return _to_group_out(group)


@router.get("/{group_id}", response_model=GroupDetailOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    return _to_group_detail(_get_group_or_404(db, group_id))


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(group_id: int, payload: GroupUpdate, db: Session = Depends(get_db)):
    group = _get_group_or_404(db, group_id)
    if payload.name is not None:
        existing = db.query(models.Group).filter(models.Group.name == payload.name).first()
        if existing and existing.id != group.id:
            raise HTTPException(status_code=400, detail="A group with this name already exists")
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    db.commit()
    db.refresh(group)
    return _to_group_out(group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = _get_group_or_404(db, group_id)
    db.delete(group)
    db.commit()


@router.put("/{group_id}/members", response_model=GroupDetailOut)
def set_group_members(group_id: int, payload: GroupMembersUpdate, db: Session = Depends(get_db)):
    group = _get_group_or_404(db, group_id)
    users = db.query(models.User).filter(models.User.id.in_(payload.user_ids)).all()
    if len(users) != len(set(payload.user_ids)):
        raise HTTPException(status_code=400, detail="One or more user ids do not exist")
    group.users = users
    db.commit()
    db.refresh(group)
    return _to_group_detail(group)


@router.put("/{group_id}/permissions", response_model=GroupDetailOut)
def set_group_permissions(group_id: int, payload: PermissionsUpdate, db: Session = Depends(get_db)):
    group = _get_group_or_404(db, group_id)

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

    db.query(models.GroupModulePermission).filter(
        models.GroupModulePermission.group_id == group.id
    ).delete()
    for grant in payload.permissions:
        module = module_cache[grant.module_name]
        db.add(models.GroupModulePermission(group_id=group.id, module_id=module.id, role=grant.role))

    db.commit()
    db.refresh(group)
    return _to_group_detail(group)
