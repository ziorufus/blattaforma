from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

user_group_association = Table(
    "user_group",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    picture: Mapped[str] = mapped_column(String(1024), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[DateTime] = mapped_column(DateTime, nullable=True)

    groups = relationship("Group", secondary=user_group_association, back_populates="users")
    module_permissions = relationship(
        "UserModulePermission", back_populates="user", cascade="all, delete-orphan"
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    users = relationship("User", secondary=user_group_association, back_populates="groups")
    module_permissions = relationship(
        "GroupModulePermission", back_populates="group", cascade="all, delete-orphan"
    )


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    discovered_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    user_permissions = relationship(
        "UserModulePermission", back_populates="module", cascade="all, delete-orphan"
    )
    group_permissions = relationship(
        "GroupModulePermission", back_populates="module", cascade="all, delete-orphan"
    )


class UserModulePermission(Base):
    __tablename__ = "user_module_permissions"
    __table_args__ = (UniqueConstraint("user_id", "module_id", "role", name="uq_user_module_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)

    user = relationship("User", back_populates="module_permissions")
    module = relationship("Module", back_populates="user_permissions")


class GroupModulePermission(Base):
    __tablename__ = "group_module_permissions"
    __table_args__ = (UniqueConstraint("group_id", "module_id", "role", name="uq_group_module_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)

    group = relationship("Group", back_populates="module_permissions")
    module = relationship("Module", back_populates="group_permissions")
