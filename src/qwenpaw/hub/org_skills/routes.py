# -*- coding: utf-8 -*-
"""HTTP routes for BeeAgent organization skill market."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .service import OrgSkillsService


class PublishBody(BaseModel):
    name: str = Field(min_length=2, max_length=63)
    display_name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    content_md: str = Field(min_length=20)
    visibility: str = Field(default="org")
    emoji: str = Field(default="🛠️", max_length=8)
    version_text: str = Field(default="1.0", max_length=32)


def org_skills_router(
    service: OrgSkillsService,
    require_user: Callable,
) -> APIRouter:
    router = APIRouter(tags=["beeagent-org-skills"])

    @router.get("/api/hub/org-skills")
    def list_org_skills(
        mine: bool = False,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        items = service.list_visible(
            is_hub_member=True,
            mine_only=mine,
            user_id=user.user_id,
        )
        return {"items": items, "official_protected": True}

    @router.post("/api/hub/org-skills", status_code=201)
    def publish_org_skill(
        body: PublishBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        try:
            return service.publish(
                name=body.name,
                display_name=body.display_name,
                description=body.description,
                content_md=body.content_md,
                visibility=body.visibility,
                emoji=body.emoji,
                version_text=body.version_text,
                owner_user_id=user.user_id,
                owner_username=user.username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/hub/org-skills/upload", status_code=201)
    async def upload_org_skill(
        user=Depends(require_user),
        file: UploadFile = File(
            ...,
            description=(
                "Skill zip (SKILL.md + optional scripts/references/assets)"
            ),
        ),
        visibility: str = Form(default="org"),
        name: str = Form(default=""),
        display_name: str = Form(default=""),
        description: str = Form(default=""),
        emoji: str = Form(default="🛠️"),
        version_text: str = Form(default="1.0"),
    ) -> dict[str, Any]:
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
            return service.publish_from_zip(
                zip_bytes=data,
                visibility=visibility,
                name_override=name,
                display_name=display_name,
                description=description,
                emoji=emoji,
                version_text=version_text,
                owner_user_id=user.user_id,
                owner_username=user.username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/hub/org-skills/{skill_id}")
    def get_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        try:
            return service.get(
                skill_id,
                is_hub_member=True,
                include_content=True,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/api/hub/org-skills/{skill_id}/install")
    def install_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        try:
            return service.install_for_user(
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

    @router.post("/api/hub/org-skills/{skill_id}/uninstall")
    def uninstall_org_skill(
        skill_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
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
        try:
            service.delete(
                skill_id,
                actor_user_id=user.user_id,
                is_admin=bool(user.is_admin),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="技能不存在") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return router
