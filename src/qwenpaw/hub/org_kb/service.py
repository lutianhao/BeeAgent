# -*- coding: utf-8 -*-
"""BeeAgent organization knowledge base service."""

from __future__ import annotations

import io
import json
import logging
import re
import sqlite3
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..database import connect_hub_database
from . import store

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_CUSTOMER_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_KB_TYPES = {"koujing", "case", "template", "customer", "other"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_CHUNK_SIZE = 900


def _normalize_customer_key(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    if not key:
        return ""
    if not _CUSTOMER_KEY_RE.match(key):
        raise ValueError(
            "客户标识须为小写字母/数字开头，仅含 a-z/0-9/_/-，最长 64",
        )
    return key


def _normalize_effective_day(raw: str | None, *, field: str) -> str:
    """Accept YYYY-MM-DD or empty; reject other shapes."""
    value = (raw or "").strip()
    if not value:
        return ""
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        day = value[:10]
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{field} 须为合法日期 YYYY-MM-DD") from exc
        return day
    raise ValueError(f"{field} 须为 YYYY-MM-DD 或留空")


class OrgKbService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.files_dir = self.database_path.parent / "org_kb"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            store.ensure_org_kb_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        return connect_hub_database(self.database_path)

    def ensure_default_libraries(self, *, created_by: str = "system") -> None:
        """Seed the four reputation KB types if missing."""
        defaults = (
            ("koujing", "口径库", "已审对外口径与禁言点"),
            ("case", "案例库", "历史舆情案例与处置复盘"),
            ("template", "模板资产库", "报告/函件/演练等正文模板"),
            ("customer", "客户资料库", "按客户隔离的负面清单与台账"),
        )
        with self._connect() as connection:
            for slug, name, description in defaults:
                if store.get_kb_by_slug(connection, slug) is None:
                    store.create_kb(
                        connection,
                        kb_id=uuid.uuid4().hex,
                        slug=slug,
                        name=name,
                        kb_type=slug if slug in _KB_TYPES else "other",
                        description=description,
                        visibility="org",
                        created_by=created_by,
                    )

    def list_libraries(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            items = store.list_kbs(connection)
            for item in items:
                docs = store.list_docs(connection, item["kb_id"])
                item["doc_count"] = len(docs)
                item["ready_count"] = sum(
                    1 for d in docs if d["status"] == "ready"
                )
            return items

    def create_library(
        self,
        *,
        slug: str,
        name: str,
        kb_type: str = "koujing",
        description: str = "",
        visibility: str = "org",
        created_by: str,
    ) -> dict[str, Any]:
        slug = slug.strip().lower()
        name = (name or slug).strip()
        kb_type = (kb_type or "other").strip().lower()
        visibility = (visibility or "org").strip().lower()
        if not _SLUG_RE.match(slug):
            raise ValueError("库标识须为小写字母开头，仅含 a-z/0-9/-，长度 2–63")
        if kb_type not in _KB_TYPES:
            raise ValueError(f"kb_type 无效，可选：{', '.join(sorted(_KB_TYPES))}")
        if visibility not in {"org", "public"}:
            raise ValueError("visibility 只能是 org 或 public")
        with self._connect() as connection:
            if store.get_kb_by_slug(connection, slug) is not None:
                raise ValueError(f"知识库已存在：{slug}")
            return store.create_kb(
                connection,
                kb_id=uuid.uuid4().hex,
                slug=slug,
                name=name,
                kb_type=kb_type,
                description=(description or "").strip(),
                visibility=visibility,
                created_by=created_by,
            )

    def delete_library(self, kb_id: str) -> None:
        with self._connect() as connection:
            docs = store.list_docs(connection, kb_id)
            if not store.soft_delete_kb(connection, kb_id):
                raise KeyError("知识库不存在")
            for doc in docs:
                store.soft_delete_doc(connection, doc["doc_id"])

    def export_library_zip(
        self,
        kb_id: str,
        *,
        user_id: str = "",
        bypass_acl: bool = False,
    ) -> tuple[bytes, str]:
        """Export one KB as a zip: manifest.json + originals/ + texts/.

        Returns ``(zip_bytes, filename)``. Customer-tagged docs respect ACL
        unless ``bypass_acl``.
        """
        with self._connect() as connection:
            kb = store.get_kb(connection, kb_id)
            if kb is None:
                raise KeyError("知识库不存在")
            docs = store.list_docs(connection, kb_id)
            if not bypass_acl:
                allowed = set(store.list_user_customer_keys(connection, user_id))
                docs = [
                    d
                    for d in docs
                    if not d.get("customer_key") or d["customer_key"] in allowed
                ]

        buf = io.BytesIO()
        root = (kb.get("slug") or kb_id)[:48]
        exported_docs: list[dict[str, Any]] = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in docs:
                entry = {
                    "doc_id": doc["doc_id"],
                    "title": doc.get("title") or "",
                    "filename": doc.get("filename") or "",
                    "content_type": doc.get("content_type") or "",
                    "status": doc.get("status") or "",
                    "customer_key": doc.get("customer_key") or "",
                    "effective_from": doc.get("effective_from") or "",
                    "effective_until": doc.get("effective_until") or "",
                    "uploaded_by": doc.get("uploaded_by") or "",
                    "created_at": doc.get("created_at") or "",
                    "updated_at": doc.get("updated_at") or "",
                    "original": None,
                    "text": None,
                }
                rel = str(doc.get("rel_path") or "")
                src = self.files_dir / rel if rel else None
                safe_name = Path(doc.get("filename") or "doc.bin").name
                stem = f"{doc['doc_id'][:12]}_{safe_name}"
                if src is not None and src.is_file():
                    arc = f"{root}/originals/{stem}"
                    zf.write(src, arc)
                    entry["original"] = arc
                # Prefer reconstructing body from chunks for portable text.
                text = self._doc_text_from_chunks(doc["doc_id"])
                if not text and src is not None and src.is_file():
                    try:
                        text = _extract_text(
                            src,
                            str(doc.get("content_type") or ""),
                        )
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        logger.warning(
                            "export extract failed doc=%s: %s",
                            doc["doc_id"],
                            exc,
                        )
                if text:
                    text_name = Path(stem).with_suffix(".md").name
                    arc = f"{root}/texts/{text_name}"
                    zf.writestr(arc, text)
                    entry["text"] = arc
                exported_docs.append(entry)

            manifest = {
                "schema": "beeagent-org-kb-export-v1",
                "exported_at": store.utc_now(),
                "library": {
                    "kb_id": kb["kb_id"],
                    "slug": kb.get("slug"),
                    "name": kb.get("name"),
                    "kb_type": kb.get("kb_type"),
                    "description": kb.get("description"),
                    "visibility": kb.get("visibility"),
                },
                "doc_count": len(exported_docs),
                "documents": exported_docs,
            }
            zf.writestr(
                f"{root}/manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )

        filename = f"org-kb-{root}-{store.utc_now()[:10]}.zip"
        return buf.getvalue(), filename

    def export_all_libraries_zip(
        self,
        *,
        user_id: str = "",
        bypass_acl: bool = False,
    ) -> tuple[bytes, str]:
        """Zip every org KB (each as its own folder) for backup."""
        libraries = self.list_libraries()
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as zf:
            index: list[dict[str, Any]] = []
            for kb in libraries:
                data, _name = self.export_library_zip(
                    kb["kb_id"],
                    user_id=user_id,
                    bypass_acl=bypass_acl,
                )
                slug = kb.get("slug") or kb["kb_id"]
                arc = f"libraries/{slug}.zip"
                zf.writestr(arc, data)
                index.append(
                    {
                        "kb_id": kb["kb_id"],
                        "slug": slug,
                        "name": kb.get("name"),
                        "archive": arc,
                        "doc_count": kb.get("doc_count"),
                    },
                )
            zf.writestr(
                "index.json",
                json.dumps(
                    {
                        "schema": "beeagent-org-kb-backup-v1",
                        "exported_at": store.utc_now(),
                        "libraries": index,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        return outer.getvalue(), f"org-kb-backup-{store.utc_now()[:10]}.zip"

    def _doc_text_from_chunks(self, doc_id: str) -> str:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT text FROM hub_org_kb_chunks "
                "WHERE doc_id = ? ORDER BY chunk_index ASC",
                (doc_id,),
            ).fetchall()
        parts = [str(r["text"] or "").strip() for r in rows]
        return "\n\n".join(p for p in parts if p)

    def list_documents(
        self,
        kb_id: str,
        *,
        user_id: str = "",
        bypass_acl: bool = False,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if store.get_kb(connection, kb_id) is None:
                raise KeyError("知识库不存在")
            docs = store.list_docs(connection, kb_id)
            if bypass_acl:
                return docs
            allowed = set(store.list_user_customer_keys(connection, user_id))
            return [
                d
                for d in docs
                if not d.get("customer_key") or d["customer_key"] in allowed
            ]

    def upload_document(
        self,
        *,
        kb_id: str,
        filename: str,
        data: bytes,
        uploaded_by: str,
        title: str = "",
        customer_key: str = "",
        effective_from: str = "",
        effective_until: str = "",
    ) -> dict[str, Any]:
        if not data:
            raise ValueError("上传文件为空")
        if len(data) > _MAX_UPLOAD_BYTES:
            raise ValueError("文件过大（上限 20MB）")
        key = _normalize_customer_key(customer_key)
        eff_from = _normalize_effective_day(effective_from, field="effective_from")
        eff_until = _normalize_effective_day(effective_until, field="effective_until")
        if eff_from and eff_until and eff_from > eff_until:
            raise ValueError("effective_from 不能晚于 effective_until")
        with self._connect() as connection:
            kb = store.get_kb(connection, kb_id)
            if kb is None:
                raise KeyError("知识库不存在")
            if kb.get("kb_type") == "customer" and not key:
                raise ValueError(
                    "客户资料库文档必须填写客户标识（customer_key），"
                    "以防跨客户串召回",
                )

        safe_name = Path(filename or "upload.txt").name
        doc_id = uuid.uuid4().hex
        rel_path = f"{kb_id}/{doc_id}_{safe_name}"
        dest = self.files_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        content_type = _guess_content_type(safe_name)
        display_title = (title or Path(safe_name).stem or safe_name).strip()
        with self._connect() as connection:
            doc = store.create_doc(
                connection,
                doc_id=doc_id,
                kb_id=kb_id,
                title=display_title,
                filename=safe_name,
                content_type=content_type,
                status="pending",
                error="",
                uploaded_by=uploaded_by,
                rel_path=rel_path,
                customer_key=key,
                effective_from=eff_from,
                effective_until=eff_until,
            )

        try:
            text = _extract_text(dest, content_type)
            chunks = _chunk_text(text)
            if not chunks:
                raise ValueError("未能从文件中提取可用文本（请上传 md/txt 或可解析文档）")
            with self._connect() as connection:
                store.insert_chunks(
                    connection,
                    kb_id=kb_id,
                    doc_id=doc_id,
                    title=display_title,
                    chunks=chunks,
                )
                store.update_doc_status(connection, doc_id, status="ready")
                doc = store.get_doc(connection, doc_id) or doc
            doc["chunk_count"] = len(chunks)
            return doc
        except Exception as exc:
            logger.warning("org kb parse failed doc=%s: %s", doc_id, exc)
            with self._connect() as connection:
                store.update_doc_status(
                    connection,
                    doc_id,
                    status="failed",
                    error=str(exc)[:500],
                )
                doc = store.get_doc(connection, doc_id) or doc
            raise ValueError(str(exc)) from exc

    def ingest_text(
        self,
        *,
        kb_id: str,
        title: str,
        text: str,
        uploaded_by: str,
        customer_key: str = "",
        effective_from: str = "",
        effective_until: str = "",
    ) -> dict[str, Any]:
        """Create a document from pasted Markdown/plain text (沉淀入库)."""
        body = (text or "").strip()
        if not body:
            raise ValueError("正文不能为空")
        if len(body.encode("utf-8")) > _MAX_UPLOAD_BYTES:
            raise ValueError("正文过大（上限 20MB）")
        display = (title or "").strip() or "未命名沉淀"
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", display)[:48] or "note"
        return self.upload_document(
            kb_id=kb_id,
            filename=f"{safe}.md",
            data=body.encode("utf-8"),
            uploaded_by=uploaded_by,
            title=display,
            customer_key=customer_key,
            effective_from=effective_from,
            effective_until=effective_until,
        )

    def delete_document(self, doc_id: str) -> None:
        with self._connect() as connection:
            doc = store.get_doc(connection, doc_id)
            if doc is None:
                raise KeyError("文档不存在")
            store.soft_delete_doc(connection, doc_id)
        path = self.files_dir / str(doc.get("rel_path") or "")
        if path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("failed to remove kb file %s: %s", path, exc)

    def search(
        self,
        *,
        query: str,
        kb_id: str | None = None,
        kb_slug: str | None = None,
        skill_name: str | None = None,
        customer_key: str | None = None,
        user_id: str = "",
        bypass_acl: bool = False,
        as_of: str | None = None,
        include_expired: bool = False,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        resolved_kb: str | None = kb_id
        bound_slugs: list[str] = []
        key_filter = _normalize_customer_key(customer_key) or None
        as_of_day = (
            _normalize_effective_day(as_of, field="as_of")
            if as_of
            else store.utc_now()[:10]
        )
        with self._connect() as connection:
            allowed_keys = (
                []
                if bypass_acl
                else store.list_user_customer_keys(connection, user_id)
            )
            if not resolved_kb and kb_slug:
                kb = store.get_kb_by_slug(connection, kb_slug.strip().lower())
                if kb is None:
                    raise KeyError(f"知识库不存在：{kb_slug}")
                resolved_kb = kb["kb_id"]
            elif not resolved_kb and skill_name:
                bound_slugs = store.get_skill_kb_slugs(
                    connection,
                    skill_name,
                )

            if bound_slugs and not resolved_kb:
                # Search bound libraries in priority order; merge unique chunks.
                merged: list[dict[str, Any]] = []
                seen: set[str] = set()
                per = max(1, min(limit, 20))
                for slug in bound_slugs:
                    kb = store.get_kb_by_slug(connection, slug)
                    if kb is None:
                        continue
                    hits = store.search_chunks(
                        connection,
                        query=query,
                        kb_id=kb["kb_id"],
                        limit=per,
                        bypass_acl=bypass_acl,
                        allowed_customer_keys=allowed_keys,
                        customer_key=key_filter,
                        as_of=as_of_day,
                        include_expired=include_expired,
                    )
                    for hit in hits:
                        cid = hit.get("chunk_id") or ""
                        if cid in seen:
                            continue
                        seen.add(str(cid))
                        hit["kb_slug"] = kb.get("slug") or slug
                        hit["kb_name"] = kb.get("name") or ""
                        hit["kb_type"] = kb.get("kb_type") or ""
                        hit["bound_skill"] = (skill_name or "").strip().lower()
                        merged.append(hit)
                        if len(merged) >= limit:
                            return merged
                return merged

            hits = store.search_chunks(
                connection,
                query=query,
                kb_id=resolved_kb,
                limit=limit,
                bypass_acl=bypass_acl,
                allowed_customer_keys=allowed_keys,
                customer_key=key_filter,
                as_of=as_of_day,
                include_expired=include_expired,
            )
            # Enrich with library slug/name for citations.
            kb_cache: dict[str, dict[str, Any]] = {}
            for hit in hits:
                kid = hit["kb_id"]
                if kid not in kb_cache:
                    kb_cache[kid] = store.get_kb(connection, kid) or {}
                kb = kb_cache[kid]
                hit["kb_slug"] = kb.get("slug") or ""
                hit["kb_name"] = kb.get("name") or ""
                hit["kb_type"] = kb.get("kb_type") or ""
            return hits

    def record_feedback(
        self,
        *,
        user_id: str,
        useful: bool,
        chunk_id: str = "",
        doc_id: str = "",
        kb_id: str = "",
        query: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        """Record whether a kb_search hit was useful (for later ranking/tuning)."""
        cid = (chunk_id or "").strip()
        did = (doc_id or "").strip()
        kid = (kb_id or "").strip()
        if not cid and not did:
            raise ValueError("需要 chunk_id 或 doc_id")
        with self._connect() as connection:
            if cid and not did:
                row = connection.execute(
                    "SELECT doc_id, kb_id FROM hub_org_kb_chunks "
                    "WHERE chunk_id = ?",
                    (cid,),
                ).fetchone()
                if row is not None:
                    did = did or str(row["doc_id"] or "")
                    kid = kid or str(row["kb_id"] or "")
            if did and not kid:
                doc = store.get_doc(connection, did)
                if doc is not None:
                    kid = str(doc.get("kb_id") or "")
            return store.insert_feedback(
                connection,
                feedback_id=uuid.uuid4().hex,
                user_id=user_id,
                chunk_id=cid,
                doc_id=did,
                kb_id=kid,
                query=query,
                useful=useful,
                note=note,
            )

    def feedback_stats(self, kb_id: str) -> dict[str, int]:
        with self._connect() as connection:
            if store.get_kb(connection, kb_id) is None:
                raise KeyError("知识库不存在")
            return store.feedback_stats_for_kb(connection, kb_id)

    def list_skill_bindings(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            store.seed_default_skill_kb_bindings(connection)
            return store.list_skill_kb_bindings(connection)

    def get_skill_bindings(self, skill_name: str) -> dict[str, Any]:
        with self._connect() as connection:
            store.seed_default_skill_kb_bindings(connection)
            slugs = store.get_skill_kb_slugs(connection, skill_name)
            return {
                "skill_name": (skill_name or "").strip().lower(),
                "kb_slugs": slugs,
            }

    def set_skill_bindings(
        self,
        skill_name: str,
        kb_slugs: list[str],
    ) -> dict[str, Any]:
        name = (skill_name or "").strip().lower()
        if not name:
            raise ValueError("skill_name 不能为空")
        with self._connect() as connection:
            # Validate slugs exist (skip empty list = clear bindings).
            for slug in kb_slugs:
                normalized = (slug or "").strip().lower()
                if not normalized:
                    continue
                if store.get_kb_by_slug(connection, normalized) is None:
                    raise ValueError(f"知识库不存在：{normalized}")
            slugs = store.set_skill_kb_bindings(
                connection,
                name,
                kb_slugs,
            )
            return {"skill_name": name, "kb_slugs": slugs}

    def list_customer_grants(
        self,
        *,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return store.list_customer_grants(connection, user_id=user_id)

    def list_known_customer_keys(self) -> list[str]:
        with self._connect() as connection:
            return store.list_known_customer_keys(connection)

    def set_user_customer_grants(
        self,
        *,
        user_id: str,
        customer_keys: list[str],
        granted_by: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            keys = store.set_user_customer_grants(
                connection,
                user_id=user_id,
                customer_keys=customer_keys,
                granted_by=granted_by,
            )
            return {"user_id": user_id.strip(), "customer_keys": keys}

    def patch_document_customer_key(
        self,
        doc_id: str,
        customer_key: str,
    ) -> dict[str, Any]:
        return self.patch_document_meta(doc_id, customer_key=customer_key)

    def patch_document_meta(
        self,
        doc_id: str,
        *,
        customer_key: str | None = None,
        effective_from: str | None = None,
        effective_until: str | None = None,
    ) -> dict[str, Any]:
        key = (
            _normalize_customer_key(customer_key)
            if customer_key is not None
            else None
        )
        eff_from = (
            _normalize_effective_day(effective_from, field="effective_from")
            if effective_from is not None
            else None
        )
        eff_until = (
            _normalize_effective_day(effective_until, field="effective_until")
            if effective_until is not None
            else None
        )
        with self._connect() as connection:
            doc = store.get_doc(connection, doc_id)
            if doc is None:
                raise KeyError("文档不存在")
            next_from = (
                eff_from
                if eff_from is not None
                else str(doc.get("effective_from") or "")
            )
            next_until = (
                eff_until
                if eff_until is not None
                else str(doc.get("effective_until") or "")
            )
            if next_from and next_until and next_from > next_until:
                raise ValueError("effective_from 不能晚于 effective_until")
            next_key = (
                key if key is not None else str(doc.get("customer_key") or "")
            )
            kb = store.get_kb(connection, doc["kb_id"])
            if kb and kb.get("kb_type") == "customer" and not next_key:
                raise ValueError("客户资料库文档不能清空客户标识")
            updated = store.update_doc_meta(
                connection,
                doc_id,
                customer_key=next_key if key is not None else None,
                effective_from=eff_from,
                effective_until=eff_until,
            )
            if updated is None:
                raise KeyError("文档不存在")
            return updated


def _guess_content_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lower.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


def _extract_text(path: Path, content_type: str) -> str:
    lower = path.name.lower()
    if lower.endswith((".md", ".txt", ".json", ".csv")) or content_type.startswith(
        "text/",
    ):
        return path.read_text(encoding="utf-8", errors="ignore")
    if lower.endswith(".docx"):
        try:
            import zipfile
            from xml.etree import ElementTree as ET

            with zipfile.ZipFile(path) as zf:
                xml = zf.read("word/document.xml")
            root = ET.fromstring(xml)
            texts: list[str] = []
            for node in root.iter():
                if node.tag.endswith("}t") and node.text:
                    texts.append(node.text)
            return "\n".join(texts)
        except Exception as exc:
            raise ValueError(f"无法解析 docx：{exc}") from exc
    if lower.endswith(".pdf") or content_type == "application/pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError(
                "服务器未安装 pypdf，无法解析 PDF；请先转为 Markdown/TXT",
            ) from exc
        try:
            reader = PdfReader(str(path))
            pages: list[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text.strip())
            joined = "\n\n".join(pages).strip()
            if not joined:
                raise ValueError(
                    "PDF 未提取到可用文本（可能是扫描件）；请 OCR 后上传 md/txt",
                )
            return joined
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"无法解析 PDF：{exc}") from exc
    raise ValueError("暂不支持该文件类型，请上传 .md / .txt / .docx / .pdf")


def _chunk_text(text: str) -> list[str]:
    # UPGRADE(embedding/chunking): tune size/overlap alongside vector indexing
    # (§7.2.1). Current path is paragraph-pack into ~_CHUNK_SIZE chars.
    cleaned = (text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs or [cleaned]:
        if not buf:
            buf = para
        elif len(buf) + 1 + len(para) <= _CHUNK_SIZE:
            buf = f"{buf}\n\n{para}"
        else:
            chunks.append(buf)
            buf = para
        while len(buf) > _CHUNK_SIZE * 2:
            chunks.append(buf[:_CHUNK_SIZE])
            buf = buf[_CHUNK_SIZE:]
    if buf:
        chunks.append(buf)
    return chunks
