# -*- coding: utf-8 -*-
"""Unified Hub authorization decisions.

BeeAgent uses a three-layer model (mature marketplace pattern):

1. **Capability (RBAC role)** — what class of actions the principal may attempt
   in this tenant (e.g. ``org_skill:publish``, ``org_skill:manage``).
2. **Ownership / resource relation** — whether the principal owns *this*
   listing (``owner_user_id``). Owners can update / delist / delete their own
   skills without holding ``org_skill:manage``.
3. **Personal install state** — install / upgrade / uninstall / pin apply to
   the caller's own install row, not the catalog listing.

Hub admin (``is_admin`` / ``*``) is break-glass and may do everything, with
actions still attributed to the admin principal in audit logs.

``share`` for org skills: owner (with publish) or manage may produce an
in-org share payload and optionally set visibility to public.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..rbac.catalog import (
    PERM_ORG_KB_MANAGE,
    PERM_ORG_KB_USE,
    PERM_ORG_KB_WRITE,
    PERM_ORG_SKILL_MANAGE,
    PERM_ORG_SKILL_PUBLISH,
    matches_permission,
)


@dataclass(frozen=True)
class AuthzContext:
    """Resolved caller for a single request."""

    user_id: str
    is_admin: bool
    permissions: frozenset[str]

    @classmethod
    def from_entitlements(
        cls,
        *,
        user_id: str,
        is_admin: bool,
        entitlements: Mapping[str, Any] | None,
    ) -> "AuthzContext":
        perms = set((entitlements or {}).get("permissions") or [])
        if is_admin:
            perms.add("*")
        return cls(
            user_id=str(user_id or ""),
            is_admin=bool(is_admin),
            permissions=frozenset(perms),
        )

    def has(self, permission: str) -> bool:
        if self.is_admin or "*" in self.permissions:
            return True
        return matches_permission(set(self.permissions), permission)


class OrgSkillAction(str, Enum):
    """Object actions on organization skill listings / installs."""

    LIST = "list"
    VIEW = "view"
    PUBLISH_NEW = "publish_new"
    UPDATE_VERSION = "update_version"
    DELIST = "delist"
    RELIST = "relist"
    FEATURE = "feature"
    RETAG = "retag"
    DELETE_LISTING = "delete_listing"
    INSTALL = "install"
    UPGRADE = "upgrade"
    UNINSTALL = "uninstall"
    PIN = "pin"
    SHARE = "share"


def _is_owner(ctx: AuthzContext, owner_user_id: str | None) -> bool:
    return bool(owner_user_id) and ctx.user_id == str(owner_user_id)


def org_skill_allowed(
    ctx: AuthzContext,
    action: OrgSkillAction,
    *,
    owner_user_id: str | None = None,
    installed: bool = False,
) -> bool:
    """Return whether ``ctx`` may perform ``action`` on an org skill.

    Ownership is required for listing mutations when the caller lacks manage.
    Install-scoped actions only need a logged-in member (and install row where
    noted).
    """
    if not ctx.user_id and not ctx.is_admin:
        return False
    if ctx.is_admin or "*" in ctx.permissions:
        return True

    can_publish = ctx.has(PERM_ORG_SKILL_PUBLISH)
    can_manage = ctx.has(PERM_ORG_SKILL_MANAGE)
    owner = _is_owner(ctx, owner_user_id)

    if action in {OrgSkillAction.LIST, OrgSkillAction.VIEW}:
        return True

    if action is OrgSkillAction.PUBLISH_NEW:
        return can_publish

    if action is OrgSkillAction.UPDATE_VERSION:
        return owner and can_publish

    if action in {OrgSkillAction.DELIST, OrgSkillAction.RELIST}:
        return (owner and can_publish) or can_manage

    if action in {OrgSkillAction.FEATURE, OrgSkillAction.RETAG}:
        return can_manage

    if action is OrgSkillAction.DELETE_LISTING:
        return (owner and can_publish) or can_manage

    if action in {
        OrgSkillAction.INSTALL,
        OrgSkillAction.UPGRADE,
        OrgSkillAction.UNINSTALL,
        OrgSkillAction.PIN,
    }:
        # Any Hub member may manage their own install row; routes/services
        # still verify the install exists for uninstall/pin.
        _ = installed
        return True

    if action is OrgSkillAction.SHARE:
        # In-org share card / optional public visibility — not external ACL yet.
        return (owner and can_publish) or can_manage

    return False


def org_skill_ops_allowed(
    ctx: AuthzContext,
    *,
    owner_user_id: str | None,
    category: str | None = None,
    featured: bool | None = None,
    status: str | None = None,
    visibility: str | None = None,
) -> tuple[bool, str]:
    """Authorize a PATCH ops payload. Owners may delist/relist/visibility only."""
    touching_manage_only = featured is not None or category is not None
    touching_owner_ops = status is not None or visibility is not None
    if not touching_manage_only and not touching_owner_ops:
        return False, "无有效运营字段"

    if touching_manage_only:
        if not org_skill_allowed(ctx, OrgSkillAction.FEATURE) and not org_skill_allowed(
            ctx,
            OrgSkillAction.RETAG,
        ):
            return False, "缺少权限：org_skill:manage（精选/分类）"
        return True, ""

    # status / visibility — owner+publish or manage
    if status is not None:
        action = (
            OrgSkillAction.RELIST
            if str(status).strip().lower() == "active"
            else OrgSkillAction.DELIST
        )
        if not org_skill_allowed(
            ctx,
            action,
            owner_user_id=owner_user_id,
        ):
            return False, "无权下架/重新上架该技能"
    if visibility is not None:
        if not org_skill_allowed(
            ctx,
            OrgSkillAction.DELIST,
            owner_user_id=owner_user_id,
        ) and not org_skill_allowed(ctx, OrgSkillAction.RETAG):
            return False, "无权修改可见性"
    return True, ""


def org_skill_capabilities(
    ctx: AuthzContext,
    *,
    owner_user_id: str | None,
    installed: bool = False,
    update_available: bool = False,
) -> dict[str, bool]:
    """UI-facing capability flags for one catalog row."""
    owner = _is_owner(ctx, owner_user_id)
    return {
        "is_owner": owner,
        "is_admin": ctx.is_admin,
        "can_publish_new": org_skill_allowed(ctx, OrgSkillAction.PUBLISH_NEW),
        "can_update_version": org_skill_allowed(
            ctx,
            OrgSkillAction.UPDATE_VERSION,
            owner_user_id=owner_user_id,
        ),
        "can_delist": org_skill_allowed(
            ctx,
            OrgSkillAction.DELIST,
            owner_user_id=owner_user_id,
        ),
        "can_relist": org_skill_allowed(
            ctx,
            OrgSkillAction.RELIST,
            owner_user_id=owner_user_id,
        ),
        "can_feature": org_skill_allowed(ctx, OrgSkillAction.FEATURE),
        "can_retag": org_skill_allowed(ctx, OrgSkillAction.RETAG),
        "can_delete_listing": org_skill_allowed(
            ctx,
            OrgSkillAction.DELETE_LISTING,
            owner_user_id=owner_user_id,
        ),
        "can_install": org_skill_allowed(ctx, OrgSkillAction.INSTALL)
        and not installed,
        "can_upgrade": org_skill_allowed(ctx, OrgSkillAction.UPGRADE)
        and installed
        and update_available,
        "can_uninstall": org_skill_allowed(
            ctx,
            OrgSkillAction.UNINSTALL,
            installed=installed,
        )
        and installed,
        "can_pin": org_skill_allowed(ctx, OrgSkillAction.PIN, installed=installed)
        and installed,
        "can_share": org_skill_allowed(
            ctx,
            OrgSkillAction.SHARE,
            owner_user_id=owner_user_id,
        ),
    }


class OrgKbAction(str, Enum):
    """Object actions on organization knowledge bases."""

    LIST = "list"
    SEARCH = "search"
    CREATE = "create"
    WRITE_DOC = "write_doc"
    DELETE_DOC = "delete_doc"
    MANAGE = "manage"
    EXPORT = "export"
    EXPORT_ALL = "export_all"


def org_kb_allowed(ctx: AuthzContext, action: OrgKbAction) -> bool:
    """Capability checks for org KB (customer ACL is applied separately)."""
    if not ctx.user_id and not ctx.is_admin:
        return False
    if ctx.is_admin or "*" in ctx.permissions:
        return True
    if action in {OrgKbAction.LIST, OrgKbAction.SEARCH, OrgKbAction.EXPORT}:
        return ctx.has(PERM_ORG_KB_USE)
    if action in {OrgKbAction.CREATE, OrgKbAction.WRITE_DOC, OrgKbAction.DELETE_DOC}:
        return ctx.has(PERM_ORG_KB_WRITE) or ctx.has(PERM_ORG_KB_MANAGE)
    if action in {OrgKbAction.MANAGE, OrgKbAction.EXPORT_ALL}:
        return ctx.has(PERM_ORG_KB_MANAGE)
    return False


def org_kb_bypass_customer_acl(ctx: AuthzContext) -> bool:
    return ctx.is_admin or ctx.has(PERM_ORG_KB_MANAGE)
