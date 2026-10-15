from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr

from .datetime_utils import UtcDatetime


# ---------- Auth ----------


class TokenPayload(BaseModel):
    sub: int
    email: str
    is_admin: bool
    exp: int | None = None


# ---------- Modules ----------


class ModulePermissionGrant(BaseModel):
    module_name: str
    role: str


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    label: str
    roles: list[str]
    enabled: bool


class ModuleEnabledUpdate(BaseModel):
    enabled: bool


class ModuleWithAccessOut(ModuleOut):
    granted_roles: list[str]


# ---------- Groups ----------


class GroupBase(BaseModel):
    name: str
    description: str | None = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class GroupOut(GroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: UtcDatetime
    member_count: int = 0


class GroupDetailOut(GroupOut):
    members: list["UserSummary"] = []
    permissions: list[ModulePermissionGrant] = []


# ---------- Users ----------


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None = None
    picture: str | None = None
    is_admin: bool
    is_active: bool


class UserCreate(BaseModel):
    email: EmailStr
    name: str | None = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    name: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


class UserOut(UserSummary):
    created_at: UtcDatetime
    last_login: UtcDatetime | None = None
    group_ids: list[int] = []


class UserDetailOut(UserOut):
    groups: list[GroupOut] = []
    permissions: list[ModulePermissionGrant] = []
    effective_permissions: dict[str, list[str]] = {}


class MeOut(UserOut):
    groups: list[GroupOut] = []
    effective_permissions: dict[str, list[str]] = {}


class UserGroupsUpdate(BaseModel):
    group_ids: list[int]


class GroupMembersUpdate(BaseModel):
    user_ids: list[int]


class PermissionsUpdate(BaseModel):
    """Full replacement of the set of (module_name, role) grants."""

    permissions: list[ModulePermissionGrant]


# ---------- Options ----------


class OptionValueUpdate(BaseModel):
    value: Any


class OptionOut(BaseModel):
    key: str
    label: str
    description: str | None = None
    json_schema: dict[str, Any]
    public: bool
    default: Any
    value: Any
    is_default: bool
    updated_at: UtcDatetime | None = None
    updated_by: str | None = None


class OptionScopeOut(BaseModel):
    scope: str
    label: str
    is_module: bool
    enabled: bool
    options: list[OptionOut]


class PublicConfigOut(BaseModel):
    options: dict[str, dict[str, Any]]
    enabled_modules: list[str]


GroupDetailOut.model_rebuild()
