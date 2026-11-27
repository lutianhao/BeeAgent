# -*- coding: utf-8 -*-
"""HTTP routes for BeeAgent organization knowledge bases."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..authz import (
    AuthzContext,
    OrgKbAction,
    org_kb_allowed,
    org_kb_bypass_customer_acl,
    record_authz_event,
)
from .service import OrgKbService


class CreateKbBody(BaseModel):
    slug: str = Field(min_length=2, max_length=63)
    name: str = Field(min_length=1, max_length=120)
    kb_type: str = Field(default="koujing", max_length=32)
    description: str = Field(default="", max_length=2000)
    visibility: str = Field(default="org")


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    kb_id: str | None = None
    kb_slug: str | None = None
    skill_name: str | None = None
    customer_key: str | None = None
    as_of: str | None = None
    include_expired: bool = False
    limit: int = Field(default=8, ge=1, le=20)


class SetBindingsBody(BaseModel):
    kb_slugs: list[str] = Field(default_factory=list, max_length=32)


class SetCustomerGrantsBody(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    customer_keys: list[str] = Field(default_factory=list, max_length=64)


class PatchDocBody(BaseModel):
    customer_key: str | None = Field(default=None, max_length=64)
    effective_from: str | None = Field(default=None, max_length=32)
    effective_until: str | None = Field(default=None, max_length=32)


class IngestTextBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=500_000)
    customer_key: str = Field(default="", max_length=64)
    effective_from: str = Field(default="", max_length=32)
    effective_until: str = Field(default="", max_length=32)


class FeedbackBody(BaseModel):
    useful: bool
    chunk_id: str = Field(default="", max_length=128)
    doc_id: str = Field(default="", max_length=64)
    kb_id: str = Field(default="", max_length=64)
    query: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)


def org_kb_router(
    service: OrgKbService,
    require_user: Callable,
    rbac: Any | None = None,
    operations: Any | None = None,
) -> APIRouter:
    router = APIRouter(tags=["beeagent-org-kb"])

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

    def _require(user, action: OrgKbAction) -> AuthzContext:
        ctx = _authz(user)
        if not org_kb_allowed(ctx, action):
            raise HTTPException(
                status_code=403,
                detail=f"缺少权限：{action.value}",
            )
        return ctx

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
            resource_type="org_kb",
            resource_id=resource_id,
            detail=detail,
        )

    @router.get("/api/hub/org-kb")
    def list_kbs(user=Depends(require_user)) -> dict[str, Any]:
        _require(user, OrgKbAction.LIST)
        service.ensure_default_libraries(created_by=user.user_id)
        return {"items": service.list_libraries()}

    @router.post("/api/hub/org-kb", status_code=201)
    def create_kb(body: CreateKbBody, user=Depends(require_user)) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.CREATE)
        try:
            created = service.create_library(
                slug=body.slug,
                name=body.name,
                kb_type=body.kb_type,
                description=body.description,
                visibility=body.visibility,
                created_by=user.user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(user, ctx, "org_kb.create", str(created.get("kb_id") or body.slug))
        return created

    @router.delete("/api/hub/org-kb/{kb_id}", status_code=204)
    def delete_kb(kb_id: str, user=Depends(require_user)) -> None:
        ctx = _require(user, OrgKbAction.MANAGE)
        try:
            service.delete_library(kb_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="知识库不存在") from exc
        _audit(user, ctx, "org_kb.delete", kb_id)

    @router.get("/api/hub/org-kb/customer-grants")
    def list_customer_grants(
        user_id: str | None = None,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.LIST)
        bypass = org_kb_bypass_customer_acl(ctx)
        if user_id and user_id != user.user_id and not bypass:
            raise HTTPException(status_code=403, detail="只能查看自己的客户授权")
        target = None if bypass and not user_id else (user_id or user.user_id)
        if bypass and not user_id:
            items = service.list_customer_grants()
        else:
            items = service.list_customer_grants(user_id=target)
        return {
            "items": items,
            "known_customer_keys": service.list_known_customer_keys(),
        }

    @router.put("/api/hub/org-kb/customer-grants")
    def put_customer_grants(
        body: SetCustomerGrantsBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.MANAGE)
        try:
            result = service.set_user_customer_grants(
                user_id=body.user_id,
                customer_keys=body.customer_keys,
                granted_by=user.user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_kb.customer_grants",
            body.user_id,
            detail={"keys": len(body.customer_keys)},
        )
        return result

    @router.get("/api/hub/org-kb/export")
    def export_all_kbs(user=Depends(require_user)) -> Response:
        """Download a zip of every org KB (manage only)."""
        ctx = _require(user, OrgKbAction.EXPORT_ALL)
        data, filename = service.export_all_libraries_zip(
            user_id=user.user_id,
            bypass_acl=True,
        )
        _audit(user, ctx, "org_kb.export_all", "all")
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @router.get("/api/hub/org-kb/bindings")
    def list_bindings(user=Depends(require_user)) -> dict[str, Any]:
        _require(user, OrgKbAction.LIST)
        service.ensure_default_libraries(created_by=user.user_id)
        return {"items": service.list_skill_bindings()}

    @router.get("/api/hub/org-kb/bindings/{skill_name}")
    def get_binding(skill_name: str, user=Depends(require_user)) -> dict[str, Any]:
        _require(user, OrgKbAction.LIST)
        return service.get_skill_bindings(skill_name)

    @router.put("/api/hub/org-kb/bindings/{skill_name}")
    def put_binding(
        skill_name: str,
        body: SetBindingsBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.MANAGE)
        try:
            result = service.set_skill_bindings(skill_name, body.kb_slugs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(user, ctx, "org_kb.bindings", skill_name)
        return result

    @router.get("/api/hub/org-kb/{kb_id}/export")
    def export_kb(kb_id: str, user=Depends(require_user)) -> Response:
        ctx = _require(user, OrgKbAction.EXPORT)
        try:
            data, filename = service.export_library_zip(
                kb_id,
                user_id=user.user_id,
                bypass_acl=org_kb_bypass_customer_acl(ctx),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="知识库不存在") from exc
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @router.get("/api/hub/org-kb/{kb_id}/docs")
    def list_docs(kb_id: str, user=Depends(require_user)) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.LIST)
        try:
            return {
                "items": service.list_documents(
                    kb_id,
                    user_id=user.user_id,
                    bypass_acl=org_kb_bypass_customer_acl(ctx),
                ),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="知识库不存在") from exc

    @router.post("/api/hub/org-kb/{kb_id}/docs/text", status_code=201)
    def ingest_text_doc(
        kb_id: str,
        body: IngestTextBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.WRITE_DOC)
        try:
            created = service.ingest_text(
                kb_id=kb_id,
                title=body.title,
                text=body.text,
                uploaded_by=user.user_id,
                customer_key=body.customer_key,
                effective_from=body.effective_from,
                effective_until=body.effective_until,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="知识库不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_kb.ingest_text",
            kb_id,
            detail={"doc_id": created.get("doc_id")},
        )
        return created

    @router.post("/api/hub/org-kb/{kb_id}/docs", status_code=201)
    async def upload_doc(
        kb_id: str,
        user=Depends(require_user),
        file: UploadFile = File(...),
        title: str = Form(default=""),
        customer_key: str = Form(default=""),
        effective_from: str = Form(default=""),
        effective_until: str = Form(default=""),
    ) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.WRITE_DOC)
        data = await file.read()
        try:
            created = service.upload_document(
                kb_id=kb_id,
                filename=file.filename or "upload.txt",
                data=data,
                uploaded_by=user.user_id,
                title=title,
                customer_key=customer_key,
                effective_from=effective_from,
                effective_until=effective_until,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="知识库不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(
            user,
            ctx,
            "org_kb.upload_doc",
            kb_id,
            detail={"doc_id": created.get("doc_id")},
        )
        return created

    @router.patch("/api/hub/org-kb/docs/{doc_id}")
    def patch_doc(
        doc_id: str,
        body: PatchDocBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.MANAGE)
        try:
            updated = service.patch_document_meta(
                doc_id,
                customer_key=body.customer_key,
                effective_from=body.effective_from,
                effective_until=body.effective_until,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="文档不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _audit(user, ctx, "org_kb.patch_doc", doc_id)
        return updated

    @router.delete("/api/hub/org-kb/docs/{doc_id}", status_code=204)
    def delete_doc(doc_id: str, user=Depends(require_user)) -> None:
        ctx = _require(user, OrgKbAction.DELETE_DOC)
        try:
            service.delete_document(doc_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="文档不存在") from exc
        _audit(user, ctx, "org_kb.delete_doc", doc_id)

    @router.post("/api/hub/org-kb/search")
    def search_kb(body: SearchBody, user=Depends(require_user)) -> dict[str, Any]:
        ctx = _require(user, OrgKbAction.SEARCH)
        bypass = org_kb_bypass_customer_acl(ctx)
        include_expired = bool(body.include_expired) and bypass
        try:
            hits = service.search(
                query=body.query,
                kb_id=body.kb_id,
                kb_slug=body.kb_slug,
                skill_name=body.skill_name,
                customer_key=body.customer_key,
                user_id=user.user_id,
                bypass_acl=bypass,
                as_of=body.as_of,
                include_expired=include_expired,
                limit=body.limit,
            )
            return {"query": body.query, "hits": hits}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/hub/org-kb/feedback", status_code=201)
    def post_feedback(
        body: FeedbackBody,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        """Mark a search hit useful / not useful (for ranking & Embedding tune-up)."""
        _require(user, OrgKbAction.SEARCH)
        try:
            return service.record_feedback(
                user_id=user.user_id,
                useful=body.useful,
                chunk_id=body.chunk_id,
                doc_id=body.doc_id,
                kb_id=body.kb_id,
                query=body.query,
                note=body.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/hub/org-kb/{kb_id}/feedback-stats")
    def get_feedback_stats(
        kb_id: str,
        user=Depends(require_user),
    ) -> dict[str, Any]:
        _require(user, OrgKbAction.LIST)
        try:
            stats = service.feedback_stats(kb_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="知识库不存在") from exc
        return {"kb_id": kb_id, **stats}

    return router
