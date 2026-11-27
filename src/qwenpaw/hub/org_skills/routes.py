# -*- coding: utf-8 -*-
"""HTTP routes for BeeAgent organization skill market."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..authz import (
    AuthzContext,
    OrgSkillAction,
    org_skill_allowed,
    org_skill_capabilities,
    org_skill_ops_allowed,
    record_authz_event,
)
from ..rbac.catalog import PERM_ORG_SKILL_MANAGE, matches_permission
from .service import OrgSkillsService


class PublishBody(BaseModel):
    name: str = Field(min_length=2, max_length=63)
    display_name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    content_md: str = Field(min_length=20)
    # Default personal: only owner sees it until listed to org.
    visibility: str = Field(default="personal")
    emoji: str = Field(default="🛠️", max_length=8)
    # Empty → create at 1.0.0 / update auto patch-bumps (see OrgSkillsService).
    version_text: str = Field(default="", max_length=32)
    changelog: str = Field(default="", max_length=4000)
    category: str = Field(default="other", max_length=32)


class OpsBody(BaseModel):
    category: str | None = Field(default=None, max_length=32)
    featured: bool | None = None
    status: str | None = Field(default=None, max_length=16)
    visibility: str | None = Field(default=None, max_length=16)


class PinBody(BaseModel):
    pinned: bool = True


class ShareBody(BaseModel):
    """Optional: flip visibility when sharing outside the org."""

    make_public: bool = False


def org_skills_router(
    service: OrgSkillsService,
    require_user: Callable,
    rbac: Any | None = None,
    operations: Any | None = None,
) -> APIRouter:
    router = APIRouter(tags=["beeagent-org-skills"])

    def _authz(user) -> AuthzContext:
        if rbac is None:
            perms: set[str] = {"*"} if user.is_admin else set()
            return AuthzContext(
                user_id=str(user.user_id or ""),
                is_admin=bool(user.is_admin),
                permissions=frozenset(perms),
            )
        ent = rbac.entitlements(user.user_id, is_hub_admin=bool(user.is_admin))
        return AuthzContext.from_entitlements(
            user_id=user.user_id,
            is_admin=bool(user.is_admin),
            entitlements=ent,
        )

    def _permission_set(user) -> set[str]:
        return set(_authz(user).permissions)

    def _attach_capabilities(ctx: AuthzContext, item: dict[str, Any]) -> dict[str, Any]:
        caps = org_skill_capabilities(
            ctx,
            owner_user_id=str(item.get("owner_user_id") or ""),
            installed=bool(item.get("installed")),
            update_available=bool(item.get("update_available")),
        )
        vis = str(item.get("visibility") or "org")
        deleted = bool(item.get("deleted_at")) or str(item.get("status")) == "deleted"
        caps["can_list_to_org"] = bool(
            caps.get("is_owner") and vis == "personal" and not deleted,
        )
        caps["can_make_personal"] = bool(
            caps.get("is_owner") and vis in {"org", "public"} and not deleted,
        )
        caps["can_restore"] = bool(
            deleted
            and (
                caps.get("is_owner")
                or caps.get("is_admin")
                or matches_permission(set(ctx.permissions), PERM_ORG_SKILL_MANAGE)
            ),
        )
        out = dict(item)
        out["capabilities"] = caps
        return out

    def _deny(detail: str) -> None:
        raise HTTPException(status_code=403, detail=detail)

    def _audit(
        user,
        ctx: AuthzContext,
        action: str,
        resource_id: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        record_authz_event(
            operations,
            ctx=ctx,
            actor_username=getattr(user, "username", "") or "",
            action=action,
            resource_type="org_skill",
            resource_id=resource_id,
            detail=detail,
        )

    @router.get("/api/hub/org-skills")
    def list_org_skills(
        mine: bool = False,
        category: str | None = None,
        include_delisted: bool = False,
        include_deleted: bool = False,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        can_manage = matches_permission(
            set(ctx.permissions),
            PERM_ORG_SKILL_MANAGE,
        ) or ctx.is_admin
        # Owners may also request their own delisted rows via mine=true.
        include = bool(include_delisted and (can_manage or mine))
        want_deleted = bool(include_deleted)
        # Recycle: non-manage always scoped to self; manage may pass mine=false for all.
        deleted_mine = want_deleted and not can_manage
        items = service.list_visible(
            is_hub_member=True,
            mine_only=mine or deleted_mine,
            user_id=user.user_id,
            include_delisted=include,
            include_deleted=want_deleted,
            category=(category or "").strip().lower() or None,
        )
        return {
            "items": [_attach_capabilities(ctx, item) for item in items],
            "official_protected": True,
            "viewer": {
                "can_publish_new": org_skill_allowed(
                    ctx,
                    OrgSkillAction.PUBLISH_NEW,
                ),
                "can_manage": can_manage,
            },
            "categories": [
                "koujing",
                "yuqing",
                "appeal",
                "report",
                "drill",
                "data",
                "tools",
                "content",
                "ops",
                "finance",
                "other",
            ],
        }

    @router.post("/api/hub/org-skills", status_code=201)
    def publish_org_skill(
        body: PublishBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        if not org_skill_allowed(ctx, OrgSkillAction.PUBLISH_NEW):
            _deny("缺少权限：org_skill:publish")
        try:
            created = service.publish(
                name=body.name,
                display_name=body.display_name,
                description=body.description,
                content_md=body.content_md,
                visibility=body.visibility,
                emoji=body.emoji,
                version_text=body.version_text,
                changelog=body.changelog,
                category=body.category,
                owner_user_id=user.user_id,
                owner_username=user.username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_skill.publish"
            if not created.get("is_update")
            else "org_skill.update_version",
            str(created.get("skill_id") or body.name),
            detail={
                "version": created.get("version_text"),
                "is_update": bool(created.get("is_update")),
            },
        )
        return created

    @router.post("/api/hub/org-skills/upload", status_code=201)
    async def upload_org_skill(
        user=Depends(require_user),
        file: UploadFile = File(
            ...,
            description=(
                "Skill zip (SKILL.md + optional scripts/references/assets)"
            ),
        ),
        visibility: str = Form(default="personal"),
        name: str = Form(default=""),
        display_name: str = Form(default=""),
        description: str = Form(default=""),
        emoji: str = Form(default="🛠️"),
        # Empty string (Console omits / clears version) → auto bump on update.
        version_text: str = Form(default=""),
        changelog: str = Form(default=""),
        category: str = Form(default="other"),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        if not org_skill_allowed(ctx, OrgSkillAction.PUBLISH_NEW):
            _deny("缺少权限：org_skill:publish")
        filename = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
        if filename and not filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="请上传 .zip 技能包")
        if content_type and "zip" not in content_type and content_type not in {
            "application/octet-stream",
            "multipart/form-data",
            "",
        }:
            raise HTTPException(
                status_code=400,
                detail=f"期望 zip 文件，收到 content-type: {file.content_type}",
            )
        data = await file.read()
        try:
            created = service.publish_from_zip(
                zip_bytes=data,
                visibility=visibility,
                name_override=name,
                display_name=display_name,
                description=description,
                emoji=emoji,
                version_text=version_text,
                changelog=changelog,
                category=category,
                owner_user_id=user.user_id,
                owner_username=user.username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_skill.publish"
            if not created.get("is_update")
            else "org_skill.update_version",
            str(created.get("skill_id") or name or "zip"),
            detail={
                "version": created.get("version_text"),
                "is_update": bool(created.get("is_update")),
            },
        )
        return created

    @router.patch("/api/hub/org-skills/{skill_id}/ops")
    def patch_org_skill_ops(
        skill_id: str,
        body: OpsBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        try:
            skill = service.get(
                skill_id,
                is_hub_member=True,
                include_content=False,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        ok, reason = org_skill_ops_allowed(
            ctx,
            owner_user_id=str(skill.get("owner_user_id") or ""),
            category=body.category,
            featured=body.featured,
            status=body.status,
            visibility=body.visibility,
        )
        if not ok:
            _deny(reason)

        try:
            updated = service.update_ops(
                skill_id,
                category=body.category,
                featured=body.featured,
                status=body.status,
                visibility=body.visibility,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_skill.ops",
            skill_id,
            detail={
                "status": body.status,
                "featured": body.featured,
                "category": body.category,
                "visibility": body.visibility,
                "owner_user_id": skill.get("owner_user_id"),
            },
        )
        return updated

    @router.post("/api/hub/org-skills/{skill_id}/share")
    def share_org_skill(
        skill_id: str,
        body: ShareBody | None = None,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        """Return an in-org share card; optionally make the listing public."""
        ctx = _authz(user)
        body = body or ShareBody()
        try:
            skill = service.get(
                skill_id,
                is_hub_member=True,
                include_content=False,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        owner_id = str(skill.get("owner_user_id") or "")
        if not org_skill_allowed(
            ctx,
            OrgSkillAction.SHARE,
            owner_user_id=owner_id,
        ):
            _deny("无权分享该组织技能")

        visibility = str(skill.get("visibility") or "org")
        if body.make_public and visibility != "public":
            ok, reason = org_skill_ops_allowed(
                ctx,
                owner_user_id=owner_id,
                visibility="public",
            )
            if not ok:
                _deny(reason)
            skill = service.update_ops(skill_id, visibility="public")
            visibility = "public"

        payload = {
            "skill_id": skill_id,
            "name": skill.get("name"),
            "display_name": skill.get("display_name") or skill.get("name"),
            "version_text": skill.get("version_text"),
            "visibility": visibility,
            "owner_username": skill.get("owner_username"),
            "share_path": f"/market?source=beeagent-org&skill={skill_id}",
            "share_text": (
                f"组织技能「{skill.get('display_name') or skill.get('name')}」"
                f" v{skill.get('version_text') or '-'}，"
                f"可在 扩展 → 技能 → 组织技能 中搜索安装。"
            ),
        }
        _audit(
            user,
            ctx,
            "org_skill.share",
            skill_id,
            detail={"make_public": bool(body.make_public), "visibility": visibility},
        )
        return payload

    @router.get("/api/hub/org-skills/{skill_id}")
    def get_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        try:
            skill = service.get(
                skill_id,
                is_hub_member=True,
                include_content=True,
            )
            service.assert_can_view(
                skill,
                user_id=str(user.user_id or ""),
                is_hub_member=True,
                is_admin=bool(user.is_admin),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        # Enrich install flags for capabilities when possible.
        items = service.list_visible(
            is_hub_member=True,
            user_id=user.user_id,
            include_delisted=True,
        )
        match = next((i for i in items if i.get("skill_id") == skill_id), None)
        if match:
            skill = {**skill, **{
                k: match.get(k)
                for k in (
                    "installed",
                    "installed_version",
                    "update_available",
                    "pinned",
                    "newer_version",
                )
                if k in match
            }}
        return _attach_capabilities(ctx, skill)

    @router.get("/api/hub/org-skills/{skill_id}/files")
    def list_org_skill_files(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        try:
            skill = service.get(skill_id, is_hub_member=True)
            service.assert_can_view(
                skill,
                user_id=str(user.user_id or ""),
                is_hub_member=True,
                is_admin=bool(user.is_admin),
            )
            files = service.list_bundle_files(
                skill_id,
                is_hub_member=True,
            )
            return {"skill_id": skill_id, "files": files}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/api/hub/org-skills/{skill_id}/install")
    def install_org_skill(
        skill_id: str,
        force: bool = False,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        if not org_skill_allowed(ctx, OrgSkillAction.INSTALL):
            _deny("无权安装组织技能")
        try:
            return service.install_for_user(
                skill_id,
                user_id=user.user_id,
                is_hub_member=True,
                force=force,
                granted_permissions=_permission_set(user),
                is_admin=bool(user.is_admin),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.put("/api/hub/org-skills/{skill_id}/pin")
    def pin_org_skill(
        skill_id: str,
        body: PinBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        """Pin/unpin the installed version (blocks upgrade until unpinned)."""
        ctx = _authz(user)
        if not org_skill_allowed(ctx, OrgSkillAction.PIN, installed=True):
            _deny("无权钉版本")
        try:
            return service.set_pin_for_user(
                skill_id,
                user_id=user.user_id,
                pinned=body.pinned,
                is_hub_member=True,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/hub/org-skills/{skill_id}/uninstall")
    def uninstall_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        if not org_skill_allowed(ctx, OrgSkillAction.UNINSTALL, installed=True):
            _deny("无权卸载")
        try:
            return service.uninstall_for_user(
                skill_id,
                user_id=user.user_id,
                is_hub_member=True,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/api/hub/org-skills/{skill_id}", status_code=204)
    def delete_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> None:
        ctx = _authz(user)
        try:
            skill = service.get(
                skill_id,
                is_hub_member=True,
                include_content=False,
            )
            service.assert_can_view(
                skill,
                user_id=str(user.user_id or ""),
                is_hub_member=True,
                is_admin=bool(user.is_admin),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        owner_id = str(skill.get("owner_user_id") or "")
        if not org_skill_allowed(
            ctx,
            OrgSkillAction.DELETE_LISTING,
            owner_user_id=owner_id,
        ):
            _deny("无权删除该组织技能货架项")

        can_manage = matches_permission(
            set(ctx.permissions),
            PERM_ORG_SKILL_MANAGE,
        )
        try:
            service.delete(
                skill_id,
                actor_user_id=user.user_id,
                is_admin=bool(user.is_admin),
                can_manage=can_manage,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_skill.delete",
            skill_id,
            detail={"owner_user_id": owner_id, "name": skill.get("name")},
        )

    @router.post("/api/hub/org-skills/{skill_id}/restore")
    def restore_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _authz(user)
        can_manage = matches_permission(
            set(ctx.permissions),
            PERM_ORG_SKILL_MANAGE,
        ) or ctx.is_admin
        try:
            restored = service.restore(
                skill_id,
                actor_user_id=user.user_id,
                is_admin=bool(user.is_admin),
                can_manage=can_manage,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_skill.restore",
            skill_id,
            detail={
                "owner_user_id": restored.get("owner_user_id"),
                "name": restored.get("name"),
                "visibility": restored.get("visibility"),
            },
        )
        return _attach_capabilities(ctx, restored)

    return router
