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
    scan_skill_dir_or_raise,
    validate_skill_content,
)

_IGNORED_SKILL_ARTIFACTS = {
    "__pycache__",
    "__MACOSX",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}
from ...exceptions import SkillsError
from ..database import connect_hub_database
from ..rbac.catalog import OFFICIAL_SKILLS
from . import store

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
    ) -> list[dict[str, Any]]:
        """Hub members see org+public; outsiders only public (if ever exposed)."""
        with self._connect() as connection:
            items = store.list_skills(
                connection,
                include_public=True,
                include_org=bool(is_hub_member),
                owner_user_id=user_id if mine_only else None,
            )
            installed = set(
                store.list_installs_for_user(connection, user_id or ""),
            )
            for item in items:
                item["installed"] = item["skill_id"] in installed
                # Reflect on-disk bundle even for legacy rows.
                if not item.get("has_bundle"):
                    item["has_bundle"] = self.bundle_path(
                        item["skill_id"],
                    ).is_file()
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
        if not skill.get("has_bundle"):
            skill["has_bundle"] = self.bundle_path(skill_id).is_file()
        return skill

    def publish(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        content_md: str,
        visibility: str = "org",
        emoji: str = "🛠️",
        version_text: str = "1.0",
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

        skill_id = uuid.uuid4().hex
        bundle = self._zip_from_skill_md(name, content_md)
        return self._persist_new_skill(
            skill_id=skill_id,
            name=name,
            display_name=display_name,
            description=description,
            emoji=emoji or "🛠️",
            visibility=visibility,
            content_md=content_md,
            version_text=version_text or "1.0",
            owner_user_id=owner_user_id,
            owner_username=owner_username,
            bundle_bytes=bundle,
        )

    def publish_from_zip(
        self,
        *,
        zip_bytes: bytes,
        visibility: str = "org",
        name_override: str = "",
        display_name: str = "",
        description: str = "",
        emoji: str = "🛠️",
        version_text: str = "1.0",
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
            if not description:
                description = declared_desc

            # Normalize zip layout to `<name>/...` so install is deterministic.
            bundle = self._zip_from_skill_dir(name, skill_dir)
            skill_id = uuid.uuid4().hex
            return self._persist_new_skill(
                skill_id=skill_id,
                name=name,
                display_name=display_name,
                description=description,
                emoji=emoji or "🛠️",
                visibility=visibility,
                content_md=content_md,
                version_text=version_text or "1.0",
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
    ) -> None:
        with self._connect() as connection:
            ok = store.soft_delete_skill(
                connection,
                skill_id,
                actor_user_id=actor_user_id,
                is_admin=is_admin,
            )
        if not ok:
            raise KeyError("skill not found")
        bundle = self.bundle_path(skill_id)
        if bundle.is_file():
            try:
                bundle.unlink()
            except OSError as exc:
                logger.warning("failed to remove org skill bundle %s: %s", skill_id, exc)

    def install_for_user(
        self,
        skill_id: str,
        *,
        user_id: str,
        is_hub_member: bool,
    ) -> dict[str, Any]:
        skill = self.get(
            skill_id,
            is_hub_member=is_hub_member,
            include_content=True,
        )
        if skill["name"] in _RESERVED:
            raise ValueError("不允许安装为官方保留技能名")

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
            )
        return {
            "skill_id": skill["skill_id"],
            "name": skill["name"],
            "runtime_id": runtime["runtime_id"],
            "installed": True,
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

    def _persist_new_skill(
        self,
        *,
        skill_id: str,
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
    ) -> dict[str, Any]:
        with self._connect() as connection:
            existing = store.get_skill_by_name(connection, name)
            if existing is not None:
                raise ValueError(f"技能名已存在: {name}")
            path = self.bundle_path(skill_id)
            path.write_bytes(bundle_bytes)
            try:
                return store.create_skill(
                    connection,
                    skill_id=skill_id,
                    name=name,
                    display_name=display_name,
                    description=description,
                    emoji=emoji,
                    visibility=visibility,
                    content_md=content_md,
                    version_text=version_text,
                    owner_user_id=owner_user_id,
                    owner_username=owner_username,
                    has_bundle=True,
                )
            except Exception:
                path.unlink(missing_ok=True)
                raise

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
        visibility = (visibility or "org").strip().lower()
        if visibility not in {"org", "public"}:
            raise ValueError("visibility 只能是 org 或 public")
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
            pool_entry = {
                "name": name,
                "description": skill.get("description") or skill.get("display_name"),
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
                "metadata": {
                    "name": name,
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
