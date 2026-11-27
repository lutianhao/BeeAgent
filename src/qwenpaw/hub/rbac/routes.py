# -*- coding: utf-8 -*-
"""HTTP routes for BeeAgent Hub RBAC extension."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import store
from .catalog import BUILTIN_ROLES, OFFICIAL_SKILLS, OFFICIAL_TOOLS
from .console_profile import build_console_profile
from .service import RbacService


class RoleBody(BaseModel):
    role_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class UserRolesBody(BaseModel):
    role_ids: list[str] = Field(default_factory=list)


class UserOverridesBody(BaseModel):
    overrides: list[dict[str, str]] = Field(default_factory=list)


class UserQuotaBody(BaseModel):
    daily_chat_limit: int | None = None
    daily_token_limit: int | None = None
    inherit_org_defaults: bool = True


class OrgDefaultsBody(BaseModel):
    daily_chat_limit: int | None = None
    daily_token_limit: int | None = None
    timezone: str | None = None


def rbac_router(
    rbac: RbacService,
    require_user: Callable,
    require_admin: Callable,
) -> APIRouter:
    router = APIRouter(tags=["beeagent-rbac"])

    def _require_rbac_manage(user) -> Any:
        ent = rbac.entitlements(user.user_id, is_hub_admin=user.is_admin)
        perms = set(ent.get("permissions") or [])
        if user.is_admin or "rbac:manage" in perms or "*" in perms:
            return user
        raise HTTPException(status_code=403, detail="缺少 rbac:manage 权限")

    @router.get("/api/hub/me/entitlements")
    def my_entitlements(user=Depends(require_user)) -> dict[str, Any]:
        return rbac.entitlements(user.user_id, is_hub_admin=user.is_admin)

    @router.get("/api/hub/me/console-profile")
    def my_console_profile(user=Depends(require_user)) -> dict[str, Any]:
        """Session profile for Console nav/feature rendering (not write authz)."""
        ent = rbac.entitlements(user.user_id, is_hub_admin=user.is_admin)
        return build_console_profile(
            ent,
            username=str(getattr(user, "username", "") or ""),
        )

    @router.get("/api/hub/rbac/catalog")
    def permission_catalog(user=Depends(require_user)) -> dict[str, Any]:
        _ = user
        return {
            "official_skills": list(OFFICIAL_SKILLS),
            "official_tools": list(OFFICIAL_TOOLS),
            "permission_examples": [
                "chat:use",
                "skill:use",
                "skill:use:*",
                "skill:use:koujing-xiezhuan",
                "tool:use",
                "tool:use:*",
                "tool:use:web_search",
                "tool:use:kb_search",
                "org_kb:use",
                "org_kb:write",
                "org_kb:manage",
                "org_skill:publish",
                "org_skill:manage",
                "rbac:manage",
                "quota:bypass",
            ],
        }

    @router.get("/api/hub/admin/rbac/roles")
    def list_roles(user=Depends(require_admin)) -> dict[str, Any]:
        _require_rbac_manage(user)
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            roles = store.list_roles(connection)
            connection.commit()
        return {"roles": roles}

    @router.post("/api/hub/admin/rbac/roles", status_code=201)
    def create_or_update_role(
        body: RoleBody,
        user=Depends(require_admin),
    ) -> dict[str, Any]:
        _require_rbac_manage(user)
        if body.role_id in BUILTIN_ROLES:
            raise HTTPException(
                status_code=400,
                detail="系统角色由 BeeAgent 目录维护，请新建自定义角色",
            )
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            try:
                role = store.upsert_role(
                    connection,
                    role_id=body.role_id,
                    name=body.name,
                    description=body.description,
                    permissions=body.permissions,
                    is_system=False,
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            connection.commit()
        return role

    @router.delete("/api/hub/admin/rbac/roles/{role_id}", status_code=204)
    def remove_role(role_id: str, user=Depends(require_admin)) -> None:
        _require_rbac_manage(user)
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            try:
                ok = store.delete_role(connection, role_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            connection.commit()
        if not ok:
            raise HTTPException(status_code=404, detail="role not found")

    @router.put("/api/hub/admin/rbac/users/{user_id}/roles")
    def put_user_roles(
        user_id: str,
        body: UserRolesBody,
        user=Depends(require_admin),
    ) -> dict[str, Any]:
        _require_rbac_manage(user)
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            try:
                role_ids = store.set_user_roles(
                    connection,
                    user_id,
                    body.role_ids,
                    assigned_by=user.user_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            connection.commit()
        return {"user_id": user_id, "role_ids": role_ids}

    @router.put("/api/hub/admin/rbac/users/{user_id}/overrides")
    def put_user_overrides(
        user_id: str,
        body: UserOverridesBody,
        user=Depends(require_admin),
    ) -> dict[str, Any]:
        _require_rbac_manage(user)
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            try:
                overrides = store.set_user_overrides(
                    connection,
                    user_id,
                    body.overrides,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            connection.commit()
        return {"user_id": user_id, "overrides": overrides}

    @router.get("/api/hub/admin/rbac/users/{user_id}/entitlements")
    def admin_user_entitlements(
        user_id: str,
        user=Depends(require_admin),
    ) -> dict[str, Any]:
        _require_rbac_manage(user)
        return rbac.entitlements(
            user_id,
            is_hub_admin=rbac.lookup_is_hub_admin(user_id),
        )

    @router.get("/api/hub/admin/rbac/users/{user_id}/quota")
    def get_quota(user_id: str, user=Depends(require_admin)) -> dict[str, Any]:
        _require_rbac_manage(user)
        ent = rbac.entitlements(user_id, is_hub_admin=False)
        return {
            "user_id": user_id,
            "quota": ent["quota"],
            "usage_today": ent["usage_today"],
            "usage_date": ent["usage_date"],
        }

    @router.put("/api/hub/admin/rbac/users/{user_id}/quota")
    def put_quota(
        user_id: str,
        body: UserQuotaBody,
        user=Depends(require_admin),
    ) -> dict[str, Any]:
        _require_rbac_manage(user)
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            row = store.set_user_quota(
                connection,
                user_id,
                daily_chat_limit=body.daily_chat_limit,
                daily_token_limit=body.daily_token_limit,
                inherit_org_defaults=body.inherit_org_defaults,
            )
            connection.commit()
        return row

    @router.get("/api/hub/admin/rbac/org-defaults")
    def get_org_defaults(user=Depends(require_admin)) -> dict[str, Any]:
        _require_rbac_manage(user)
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            data = store.get_org_defaults(connection)
            connection.commit()
        return data

    @router.put("/api/hub/admin/rbac/org-defaults")
    def put_org_defaults(
        body: OrgDefaultsBody,
        user=Depends(require_admin),
    ) -> dict[str, Any]:
        _require_rbac_manage(user)
        payload = {k: v for k, v in body.model_dump().items() if v is not None}
        with rbac._connect() as connection:
            store.ensure_rbac_schema(connection)
            data = store.set_org_defaults(connection, payload)
            connection.commit()
        return data

    return router
