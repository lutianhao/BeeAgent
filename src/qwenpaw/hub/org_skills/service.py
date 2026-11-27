# -*- coding: utf-8 -*-
"""BeeAgent organization skill market service."""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from ...agents.skill_system.store import (
    extract_zip_skills,
    parse_skill_requirements,
    scan_skill_dir_or_raise,
    validate_skill_content,
)
from ...exceptions import SkillsError
from ..database import connect_hub_database
from ..rbac.catalog import OFFICIAL_SKILLS, matches_permission, tool_permission
from . import store

_IGNORED_SKILL_ARTIFACTS = {
    "__pycache__",
    "__MACOSX",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_OFFICIAL = set(OFFICIAL_SKILLS)
_RESERVED = _OFFICIAL | {
    "default",
    "docx",
    "docx-zh",
    "docx-en",
    "xlsx",
    "xlsx-zh",
    "xlsx-en",
}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?$"
)
# Description should hint when to use the skill (Agent Skills progressive load).
_USE_CASE_HINT_RE = re.compile(
    r"(何时|适用|用于|当.{0,12}(时|用)|use when|when to|适用于)",
    re.IGNORECASE,
)


def normalize_version(text: str | None, *, default: str = "1.0.0") -> str:
    raw = (text or "").strip()
    if not raw:
        return default
    match = _VERSION_RE.match(raw)
    if not match:
        # Keep custom labels (e.g. "2026.11.24") but strip spaces.
        return raw
    major = int(match.group("major"))
    minor = int(match.group("minor") or 0)
    patch = int(match.group("patch") or 0)
    return f"{major}.{minor}.{patch}"


def bump_patch_version(text: str | None) -> str:
    current = normalize_version(text)
    match = _VERSION_RE.match(current)
    if not match:
        return f"{current}+1"
    major = int(match.group("major"))
    minor = int(match.group("minor") or 0)
    patch = int(match.group("patch") or 0)
    return f"{major}.{minor}.{patch + 1}"


class OrgSkillsService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.bundles_dir = self.database_path.parent / "org_skills"
        self.bundles_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            store.ensure_org_skills_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        return connect_hub_database(self.database_path)

    def bundle_path(self, skill_id: str) -> Path:
        return self.bundles_dir / f"{skill_id}.zip"

    def list_visible(
        self,
        *,
        is_hub_member: bool,
        mine_only: bool = False,
        user_id: str | None = None,
        include_delisted: bool = False,
        include_deleted: bool = False,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hub members see org+public (+ own personal); outsiders only public."""
        with self._connect() as connection:
            items = store.list_skills(
                connection,
                include_public=True,
                include_org=bool(is_hub_member) and not include_deleted,
                include_personal_for=(user_id or None)
                if (is_hub_member or mine_only or include_deleted)
                else None,
                owner_user_id=user_id if (mine_only or include_deleted) else None,
                include_delisted=include_delisted,
                include_deleted=include_deleted,
                category=category,
            )
            installs = store.list_installs_for_user(connection, user_id or "")
            install_counts = store.count_installs(
                connection,
                [item["skill_id"] for item in items],
            )
            for item in items:
                skill_id = item["skill_id"]
                state = installs.get(skill_id) or {}
                installed = skill_id in installs
                installed_version = str(state.get("installed_version") or "")
                pinned = bool(state.get("pinned"))
                item["installed"] = installed
                item["installed_version"] = installed_version
                item["pinned"] = pinned if installed else False
                item["install_count"] = install_counts.get(skill_id, 0)
                catalog_version = str(item.get("version_text") or "")
                # Compare normalized semver so "1.0" vs "1.0.0" is not a false update.
                version_differs = bool(
                    installed
                    and installed_version
                    and catalog_version
                    and normalize_version(installed_version)
                    != normalize_version(catalog_version),
                )
                # Pinned installs stay on the locked version — no update nudge.
                item["update_available"] = bool(version_differs and not pinned)
                item["newer_version"] = (
                    catalog_version if version_differs else ""
                )
                # Reflect on-disk bundle even for legacy rows.
                if not item.get("has_bundle"):
                    item["has_bundle"] = self.bundle_path(skill_id).is_file()
            return items

    def get(
        self,
        skill_id: str,
        *,
        is_hub_member: bool,
        include_content: bool = False,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            skill = store.get_skill(
                connection,
                skill_id,
                include_content=include_content,
            )
        if skill is None:
            raise KeyError("skill not found")
        if skill["visibility"] == "org" and not is_hub_member:
            raise PermissionError("组织内部技能不可对外检索")
        if skill["visibility"] == "personal":
            # Caller must enforce owner/admin; get() alone cannot see user_id.
            pass
        if not skill.get("has_bundle"):
            skill["has_bundle"] = self.bundle_path(skill_id).is_file()
        with self._connect() as connection:
            counts = store.count_installs(connection, [skill_id])
            skill["install_count"] = counts.get(skill_id, 0)
        return skill

    def assert_can_view(
        self,
        skill: dict[str, Any],
        *,
        user_id: str,
        is_hub_member: bool,
        is_admin: bool = False,
    ) -> None:
        vis = str(skill.get("visibility") or "org")
        owner = str(skill.get("owner_user_id") or "")
        if vis == "public":
            return
        if vis == "org":
            if not is_hub_member and not is_admin:
                raise PermissionError("组织内部技能不可对外检索")
            return
        if vis == "personal":
            if is_admin or (user_id and user_id == owner):
                return
            raise PermissionError("个人技能仅发布者可见")
        raise PermissionError("未知可见性")

    def update_ops(
        self,
        skill_id: str,
        *,
        category: str | None = None,
        featured: bool | None = None,
        status: str | None = None,
        visibility: str | None = None,
    ) -> dict[str, Any]:
        if category is not None:
            category = self._normalize_category(category)
        if visibility is not None:
            visibility = (visibility or "org").strip().lower()
            if visibility not in {"org", "public", "personal"}:
                raise ValueError("visibility 只能是 personal、org 或 public")
        with self._connect() as connection:
            updated = store.update_skill_ops(
                connection,
                skill_id,
                category=category,
                featured=featured,
                status=status,
                visibility=visibility,
            )
        if updated is None:
            raise KeyError("skill not found")
        return updated

    @staticmethod
    def _normalize_category(category: str) -> str:
        value = (category or "other").strip().lower() or "other"
        # Business domains (official-aligned) + general domains for personal tools.
        allowed = {
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
        }
        if value not in allowed:
            raise ValueError(
                "业务域无效，可选：koujing/yuqing/appeal/report/drill/data/"
                "tools/content/ops/finance/other",
            )
        return value

    def list_bundle_files(
        self,
        skill_id: str,
        *,
        is_hub_member: bool,
    ) -> list[dict[str, Any]]:
        """Return relative file paths inside the published zip (for detail UI)."""
        skill = self.get(skill_id, is_hub_member=is_hub_member)
        path = self.bundle_path(skill_id)
        if not path.is_file():
            # Markdown-only legacy: expose SKILL.md virtual entry.
            return [
                {
                    "path": f"{skill['name']}/SKILL.md",
                    "size": len(str(skill.get("content_md") or "").encode("utf-8")),
                },
            ]
        files: list[dict[str, Any]] = []
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if not name or name.endswith("/"):
                    continue
                base = name.split("/")[-1]
                if base in _IGNORED_SKILL_ARTIFACTS or "__MACOSX/" in name:
                    continue
                files.append({"path": name, "size": int(info.file_size)})
        files.sort(key=lambda item: str(item["path"]))
        return files

    def publish(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        content_md: str,
        visibility: str = "personal",
        emoji: str = "🛠️",
        version_text: str = "1.0",
        changelog: str = "",
        category: str = "other",
        owner_user_id: str,
        owner_username: str,
    ) -> dict[str, Any]:
        name, display_name, description, content_md, visibility = (
            self._normalize_publish_fields(
                name=name,
                display_name=display_name,
                description=description,
                content_md=content_md,
                visibility=visibility,
            )
        )
        category = self._normalize_category(category)
        if not content_md.startswith("---"):
            raise ValueError("SKILL.md 须以 YAML frontmatter（---）开头")
        try:
            declared_name, declared_desc = validate_skill_content(content_md)
        except SkillsError as exc:
            raise ValueError(str(exc)) from exc
        if declared_name != name:
            raise ValueError(
                f"技能名须与 SKILL.md frontmatter name 一致（{declared_name}）",
            )
        if not description:
            description = declared_desc
        self._require_use_case_description(description)

        bundle = self._zip_from_skill_md(name, content_md)
        return self._persist_skill(
            name=name,
            display_name=display_name,
            description=description,
            emoji=emoji or "🛠️",
            visibility=visibility,
            content_md=content_md,
            version_text=version_text,
            changelog=changelog,
            category=category,
            owner_user_id=owner_user_id,
            owner_username=owner_username,
            bundle_bytes=bundle,
        )

    def publish_from_zip(
        self,
        *,
        zip_bytes: bytes,
        visibility: str = "personal",
        name_override: str = "",
        display_name: str = "",
        description: str = "",
        emoji: str = "🛠️",
        version_text: str = "1.0",
        changelog: str = "",
        category: str = "other",
        owner_user_id: str,
        owner_username: str,
    ) -> dict[str, Any]:
        if not zip_bytes:
            raise ValueError("上传文件为空")
        if len(zip_bytes) > _MAX_UPLOAD_BYTES:
            raise ValueError("技能包过大（上限 50MB）")

        tmp_dir: Path | None = None
        try:
            try:
                tmp_dir, found = extract_zip_skills(zip_bytes)
            except SkillsError as exc:
                raise ValueError(str(exc)) from exc
            if len(found) != 1:
                raise ValueError(
                    "组织技能发布每次只支持一个技能包"
                    f"（当前检测到 {len(found)} 个）",
                )
            skill_dir, resolved_name = found[0]
            content_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            try:
                declared_name, declared_desc = validate_skill_content(content_md)
                scan_skill_dir_or_raise(skill_dir, declared_name)
            except SkillsError as exc:
                raise ValueError(str(exc)) from exc

            name = (name_override or declared_name or resolved_name).strip().lower()
            if declared_name and name_override and name != declared_name:
                raise ValueError(
                    "覆盖名须与 SKILL.md frontmatter name 一致，"
                    f"当前为 {declared_name}",
                )
            if not name_override:
                name = declared_name

            name, display_name, description, content_md, visibility = (
                self._normalize_publish_fields(
                    name=name,
                    display_name=display_name or declared_name,
                    description=description or declared_desc,
                    content_md=content_md,
                    visibility=visibility,
                )
            )
            category = self._normalize_category(category)
            if not description:
                description = declared_desc
            self._require_use_case_description(description)

            # Normalize zip layout to `<name>/...` so install is deterministic.
            bundle = self._zip_from_skill_dir(name, skill_dir)
            return self._persist_skill(
                name=name,
                display_name=display_name,
                description=description,
                emoji=emoji or "🛠️",
                visibility=visibility,
                content_md=content_md,
                version_text=version_text,
                changelog=changelog,
                category=category,
                owner_user_id=owner_user_id,
                owner_username=owner_username,
                bundle_bytes=bundle,
            )
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def delete(
        self,
        skill_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
        can_manage: bool = False,
    ) -> None:
        """Soft-delete listing; keep zip on disk for the retention window."""
        with self._connect() as connection:
            ok = store.soft_delete_skill(
                connection,
                skill_id,
                actor_user_id=actor_user_id,
                is_admin=is_admin,
                can_manage=can_manage,
            )
        if not ok:
            raise KeyError("skill not found")

    def restore(
        self,
        skill_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
        can_manage: bool = False,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            restored = store.restore_soft_deleted_skill(
                connection,
                skill_id,
                actor_user_id=actor_user_id,
                is_admin=is_admin,
                can_manage=can_manage,
            )
        if restored is None:
            raise KeyError("skill not found")
        if not restored.get("has_bundle"):
            restored["has_bundle"] = self.bundle_path(skill_id).is_file()
        return restored

    def purge_deleted(
        self,
        *,
        older_than_days: int = 7,
    ) -> list[str]:
        """Hard-delete soft-deleted skills past retention; remove zips."""
        from datetime import datetime, timedelta, timezone

        if older_than_days < 1:
            raise ValueError("older_than_days must be >= 1")
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        purged: list[str] = []
        with self._connect() as connection:
            rows = store.list_purgeable_skills(
                connection,
                older_than_iso=cutoff,
            )
            for row in rows:
                sid = str(row["skill_id"])
                store.hard_delete_skill(connection, sid)
                purged.append(sid)
        for sid in purged:
            bundle = self.bundle_path(sid)
            if bundle.is_file():
                try:
                    bundle.unlink()
                except OSError as exc:
                    logger.warning(
                        "failed to remove purged org skill bundle %s: %s",
                        sid,
                        exc,
                    )
        return purged

    def install_for_user(
        self,
        skill_id: str,
        *,
        user_id: str,
        is_hub_member: bool,
        force: bool = False,
        granted_permissions: set[str] | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        skill = self.get(
            skill_id,
            is_hub_member=is_hub_member,
            include_content=True,
        )
        self.assert_can_view(
            skill,
            user_id=user_id,
            is_hub_member=is_hub_member,
            is_admin=is_admin,
        )
        if skill["name"] in _RESERVED:
            raise ValueError("不允许安装为官方保留技能名")
        if str(skill.get("status") or "active") != "active":
            raise ValueError("该技能已下架，无法安装")

        # Compatibility gate: declared allowed-tools must be in the user's RBAC.
        if granted_permissions is not None:
            missing = self._missing_allowed_tools(
                skill.get("allowed_tools") or [],
                granted_permissions,
            )
            if missing:
                raise ValueError(
                    "当前账号缺少该技能声明的工具权限："
                    + ", ".join(missing)
                    + "（请联系管理员开通，或改用兼容环境）",
                )

        catalog_version = str(skill.get("version_text") or "")
        with self._connect() as connection:
            existing = store.get_install(
                connection,
                user_id=user_id,
                skill_id=skill_id,
            )
        if (
            existing
            and existing.get("pinned")
            and not force
            and existing.get("installed_version")
            and catalog_version
            and existing["installed_version"] != catalog_version
        ):
            raise ValueError(
                "已钉住当前版本，请先解钉再升级"
                f"（已装 {existing['installed_version']} → "
                f"货架 {catalog_version}）",
            )

        runtime = self._personal_runtime(user_id)
        if runtime is None:
            raise RuntimeError("个人运行时尚未创建，请先打开一次对话")
        working = Path(runtime["working_dir"])
        if not working.exists():
            raise RuntimeError(f"运行时工作目录不存在: {working}")

        self._write_into_runtime(working, skill)
        with self._connect() as connection:
            store.record_install(
                connection,
                user_id=user_id,
                skill_id=skill_id,
                runtime_id=str(runtime["runtime_id"]),
                installed_version=catalog_version,
            )
            if force and existing and existing.get("pinned"):
                # Forced upgrade keeps the pin on the new version.
                store.set_install_pinned(
                    connection,
                    user_id=user_id,
                    skill_id=skill_id,
                    pinned=True,
                )
        return {
            "skill_id": skill["skill_id"],
            "name": skill["name"],
            "runtime_id": runtime["runtime_id"],
            "installed": True,
            "version_text": catalog_version,
            "pinned": bool(existing.get("pinned")) if existing else False,
        }

    def set_pin_for_user(
        self,
        skill_id: str,
        *,
        user_id: str,
        pinned: bool,
        is_hub_member: bool,
    ) -> dict[str, Any]:
        """Pin/unpin the user's installed version of an org skill."""
        skill = self.get(
            skill_id,
            is_hub_member=is_hub_member,
            include_content=False,
        )
        with self._connect() as connection:
            state = store.set_install_pinned(
                connection,
                user_id=user_id,
                skill_id=skill_id,
                pinned=pinned,
            )
        if state is None:
            raise ValueError("请先安装该技能再钉版本")
        catalog_version = str(skill.get("version_text") or "")
        installed_version = str(state.get("installed_version") or "")
        version_differs = bool(
            installed_version
            and catalog_version
            and normalize_version(installed_version)
            != normalize_version(catalog_version),
        )
        return {
            "skill_id": skill["skill_id"],
            "name": skill["name"],
            "installed": True,
            "installed_version": installed_version,
            "pinned": bool(state.get("pinned")),
            "update_available": bool(version_differs and not pinned),
            "newer_version": catalog_version if version_differs else "",
            "version_text": catalog_version,
        }

    def uninstall_for_user(
        self,
        skill_id: str,
        *,
        user_id: str,
        is_hub_member: bool,
    ) -> dict[str, Any]:
        skill = self.get(
            skill_id,
            is_hub_member=is_hub_member,
            include_content=False,
        )
        if skill["name"] in _RESERVED:
            raise ValueError("不允许卸载官方保留技能名")

        runtime = self._personal_runtime(user_id)
        if runtime is None:
            raise RuntimeError("个人运行时尚未创建")
        working = Path(runtime["working_dir"])
        if working.exists():
            self._remove_from_runtime(working, skill["name"])

        with self._connect() as connection:
            store.remove_install(
                connection,
                user_id=user_id,
                skill_id=skill_id,
            )
        return {
            "skill_id": skill["skill_id"],
            "name": skill["name"],
            "runtime_id": runtime["runtime_id"],
            "installed": False,
        }

    @staticmethod
    def _extract_compatibility(content_md: str) -> tuple[str, list[str]]:
        """Parse agentskills ``compatibility`` + ``allowed-tools`` (+ requires).

        Returns ``(compatibility_text, allowed_tools)``. Tools may also come
        from ``metadata.*.requires`` bins (surfaced as soft hints only for
        install; install hard-checks ``allowed-tools`` / ``allowed_tools``).
        """
        try:
            import frontmatter  # local: same dep as skill_system
        except ImportError:
            return "", []
        try:
            post = frontmatter.loads(content_md or "")
        except Exception:  # pylint: disable=broad-exception-caught
            return "", []
        meta = post.metadata if isinstance(post.metadata, dict) else {}
        compat = str(
            meta.get("compatibility") or meta.get("compat") or "",
        ).strip()
        raw_tools = meta.get("allowed-tools")
        if raw_tools is None:
            raw_tools = meta.get("allowed_tools")
        tools: list[str] = []
        if isinstance(raw_tools, str):
            tools = [t.strip() for t in re.split(r"[\s,]+", raw_tools) if t.strip()]
        elif isinstance(raw_tools, list):
            tools = [str(t).strip() for t in raw_tools if str(t).strip()]
        # Append declared binary requirements into compatibility note if empty.
        reqs, _errs = parse_skill_requirements(meta)
        if reqs.require_bins and not compat:
            compat = "需要命令行: " + ", ".join(reqs.require_bins)
        elif reqs.require_bins and "需要命令行" not in compat:
            compat = f"{compat}；需要命令行: {', '.join(reqs.require_bins)}"
        # Dedupe tools preserving order.
        seen: set[str] = set()
        cleaned: list[str] = []
        for tool in tools:
            key = tool.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(tool)
        return compat[:500], cleaned[:32]

    def _persist_skill(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        emoji: str,
        visibility: str,
        content_md: str,
        version_text: str,
        owner_user_id: str,
        owner_username: str,
        bundle_bytes: bytes,
        changelog: str = "",
        category: str = "other",
    ) -> dict[str, Any]:
        """Create or update (owner-only) an org skill; refresh updated_at."""
        changelog = (changelog or "").strip()
        category = self._normalize_category(category)
        compat, allowed = self._extract_compatibility(content_md)
        allowed_json = json.dumps(allowed, ensure_ascii=False)
        with self._connect() as connection:
            existing = store.get_skill_by_name(connection, name)
            if existing is None:
                skill_id = uuid.uuid4().hex
                resolved_version = normalize_version(
                    version_text,
                    default="1.0.0",
                )
                path = self.bundle_path(skill_id)
                path.write_bytes(bundle_bytes)
                try:
                    created = store.create_skill(
                        connection,
                        skill_id=skill_id,
                        name=name,
                        display_name=display_name,
                        description=description,
                        emoji=emoji,
                        visibility=visibility,
                        content_md=content_md,
                        version_text=resolved_version,
                        owner_user_id=owner_user_id,
                        owner_username=owner_username,
                        has_bundle=True,
                        changelog=changelog,
                        category=category,
                        compatibility=compat,
                        allowed_tools=allowed_json,
                    )
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                created["is_update"] = False
                created["previous_version"] = None
                return created

            if str(existing["owner_user_id"]) != owner_user_id:
                raise ValueError(f"技能名已存在: {name}")

            previous = str(existing.get("version_text") or "1.0.0")
            if (version_text or "").strip():
                resolved_version = normalize_version(version_text)
            else:
                resolved_version = bump_patch_version(previous)

            skill_id = str(existing["skill_id"])
            path = self.bundle_path(skill_id)
            path.write_bytes(bundle_bytes)
            # Keep previous changelog when republish leaves the field blank.
            next_changelog = changelog or str(existing.get("changelog") or "")
            updated = store.update_skill(
                connection,
                skill_id=skill_id,
                display_name=display_name,
                description=description,
                emoji=emoji,
                visibility=visibility,
                content_md=content_md,
                version_text=resolved_version,
                has_bundle=True,
                changelog=next_changelog,
                category=category,
                compatibility=compat,
                allowed_tools=allowed_json,
            )
            updated["is_update"] = True
            updated["previous_version"] = previous
            return updated

    @staticmethod
    def _missing_allowed_tools(
        allowed_tools: list[str] | Any,
        granted: set[str],
    ) -> list[str]:
        if not allowed_tools:
            return []
        if not isinstance(allowed_tools, list):
            return []
        missing: list[str] = []
        for raw in allowed_tools:
            name = str(raw or "").strip()
            if not name:
                continue
            needed = tool_permission(name)
            if not matches_permission(granted, needed):
                missing.append(name)
        return missing

    def _require_use_case_description(self, description: str) -> None:
        text = (description or "").strip()
        if len(text) < 12:
            raise ValueError(
                "描述过短：请写清技能做什么，以及何时使用（便于对话自动命中）",
            )
        if not _USE_CASE_HINT_RE.search(text):
            raise ValueError(
                "描述须包含适用场景提示（如「何时」「适用」「用于」「Use when」）",
            )

    def _normalize_publish_fields(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        content_md: str,
        visibility: str,
    ) -> tuple[str, str, str, str, str]:
        name = name.strip().lower()
        display_name = display_name.strip() or name
        description = (description or "").strip()
        content_md = (content_md or "").strip()
        visibility = (visibility or "personal").strip().lower()
        if visibility not in {"org", "public", "personal"}:
            raise ValueError("visibility 只能是 personal、org 或 public")
        if not _NAME_RE.match(name):
            raise ValueError(
                "技能名须为小写字母开头，仅含 a-z / 0-9 / -，长度 2–63",
            )
        if name in _RESERVED:
            raise ValueError("不允许使用或覆盖官方专项 / 保留技能名")
        return name, display_name, description, content_md, visibility

    def _personal_runtime(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT runtime_id, storage_json FROM runtimes "
                "WHERE owner_user_id = ? AND deleted_at IS NULL "
                "ORDER BY created_at ASC LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        storage = json.loads(str(row["storage_json"] or "{}"))
        working = storage.get("working_dir") or ""
        return {
            "runtime_id": str(row["runtime_id"]),
            "working_dir": working,
        }

    def _write_into_runtime(
        self,
        working: Path,
        skill: dict[str, Any],
    ) -> None:
        name = skill["name"]
        skill_id = str(skill["skill_id"])
        now = store.utc_now()
        source_dir = self._materialize_skill_dir(skill)
        try:
            pool_root = working / "skill_pool"
            ws = working / "workspaces" / "default"
            ws.mkdir(parents=True, exist_ok=True)
            self._replace_skill_dir(pool_root, name, source_dir)
            self._replace_skill_dir(ws / "skills", name, source_dir)

            pool_manifest_path = pool_root / "skill.json"
            pool_manifest = _load_json(
                pool_manifest_path,
                {
                    "schema_version": "skill-pool-manifest.v1",
                    "version": 0,
                    "skills": {},
                    "builtin_skill_names": [],
                },
            )
            display_name = str(
                skill.get("display_name") or skill.get("description") or name,
            ).strip() or name
            pool_entry = {
                "name": name,
                "display_name": display_name,
                "description": skill.get("description") or display_name,
                "version_text": skill.get("version_text") or "1.0",
                "emoji": skill.get("emoji") or "🛠️",
                "commit_text": "",
                "source": "customized",
                "protected": False,
                "requirements": {
                    "require_bins": [],
                    "require_envs": [],
                    "require_mcps": [],
                },
                "updated_at": now,
                "tags": ["specialized", "org_skills"],
                "installation_origin": {
                    "kind": "local",
                    "provider": "BeeAgent",
                    "label": "org_skills",
                },
                "installed_from": f"hub-org-skills:{skill_id}",
            }
            pool_manifest.setdefault("skills", {})[name] = pool_entry
            _write_json(pool_manifest_path, pool_manifest)

            skill_json_path = ws / "skill.json"
            skill_json = _load_json(
                skill_json_path,
                {
                    "schema_version": "workspace-skill-manifest.v1",
                    "version": 0,
                    "skills": {},
                },
            )
            skill_json.setdefault("skills", {})[name] = {
                "enabled": True,
                "channels": ["all"],
                "preload": False,
                "source": "customized",
                "display_name": display_name,
                "metadata": {
                    "name": name,
                    "display_name": display_name,
                    "description": pool_entry["description"],
                    "version_text": pool_entry["version_text"],
                    "emoji": pool_entry["emoji"],
                    "commit_text": "",
                    "source": "customized",
                    "protected": False,
                    "requirements": pool_entry["requirements"],
                    "updated_at": now,
                    "tags": ["specialized", "org_skills"],
                    "beeagent": {
                        "specialized": True,
                        "from_org_market": True,
                        "visibility": skill.get("visibility") or "org",
                        "display_name": display_name,
                    },
                },
                "requirements": pool_entry["requirements"],
                "updated_at": now,
                "config": {},
                "installation_origin": pool_entry["installation_origin"],
                "installed_from": pool_entry["installed_from"],
                "tags": ["specialized", "org_skills"],
            }
            _write_json(skill_json_path, skill_json)
        finally:
            shutil.rmtree(source_dir.parent, ignore_errors=True)

    def _materialize_skill_dir(self, skill: dict[str, Any]) -> Path:
        """Return a temp skill directory (parent is temp root; caller cleans)."""
        name = skill["name"]
        skill_id = str(skill["skill_id"])
        bundle = self.bundle_path(skill_id)
        tmp_root = Path(tempfile.mkdtemp(prefix="qwenpaw_org_skill_install_"))
        skill_dir = tmp_root / name
        if bundle.is_file():
            tmp_extract: Path | None = None
            try:
                data = bundle.read_bytes()
                tmp_extract, found = extract_zip_skills(data)
                src, _ = found[0]
                shutil.copytree(
                    src,
                    skill_dir,
                    ignore=lambda _d, names: {
                        n for n in names if n in _IGNORED_SKILL_ARTIFACTS
                    },
                )
            except SkillsError:
                # Corrupt bundle: fall back to content_md.
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(
                    str(skill.get("content_md") or ""),
                    encoding="utf-8",
                )
            finally:
                if tmp_extract is not None:
                    shutil.rmtree(tmp_extract, ignore_errors=True)
            return skill_dir

        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            str(skill.get("content_md") or ""),
            encoding="utf-8",
        )
        return skill_dir

    @staticmethod
    def _replace_skill_dir(root: Path, name: str, source: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        target = root / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(
            source,
            target,
            ignore=lambda _d, names: {
                n for n in names if n in _IGNORED_SKILL_ARTIFACTS
            },
        )

    def _remove_from_runtime(self, working: Path, name: str) -> None:
        pool_root = working / "skill_pool"
        ws = working / "workspaces" / "default"
        for target in (pool_root / name, ws / "skills" / name):
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

        pool_manifest_path = pool_root / "skill.json"
        if pool_manifest_path.exists():
            pool_manifest = _load_json(pool_manifest_path, {})
            skills = pool_manifest.get("skills")
            if isinstance(skills, dict) and name in skills:
                skills.pop(name, None)
                _write_json(pool_manifest_path, pool_manifest)

        skill_json_path = ws / "skill.json"
        if skill_json_path.exists():
            skill_json = _load_json(skill_json_path, {})
            skills = skill_json.get("skills")
            if isinstance(skills, dict) and name in skills:
                skills.pop(name, None)
                _write_json(skill_json_path, skill_json)

    @staticmethod
    def _zip_from_skill_md(name: str, content_md: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{name}/SKILL.md", content_md)
        return buf.getvalue()

    @staticmethod
    def _zip_from_skill_dir(name: str, skill_dir: Path) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(skill_dir.rglob("*")):
                if not path.is_file():
                    continue
                if path.name in _IGNORED_SKILL_ARTIFACTS:
                    continue
                rel = path.relative_to(skill_dir).as_posix()
                if any(part in _IGNORED_SKILL_ARTIFACTS for part in rel.split("/")):
                    continue
                zf.write(path, f"{name}/{rel}")
        return buf.getvalue()


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-exception-caught
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
