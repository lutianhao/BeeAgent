# -*- coding: utf-8 -*-
"""Unit tests for Hub authz three-layer org-skill policy."""

from qwenpaw.hub.authz import (
    AuthzContext,
    OrgSkillAction,
    org_skill_allowed,
    org_skill_capabilities,
    org_skill_ops_allowed,
)


def _ctx(user_id: str, *perms: str, admin: bool = False) -> AuthzContext:
    return AuthzContext(
        user_id=user_id,
        is_admin=admin,
        permissions=frozenset(perms),
    )


def test_owner_can_update_and_delist_with_publish():
    owner = _ctx("u1", "org_skill:publish")
    assert org_skill_allowed(
        owner,
        OrgSkillAction.UPDATE_VERSION,
        owner_user_id="u1",
    )
    assert org_skill_allowed(
        owner,
        OrgSkillAction.DELIST,
        owner_user_id="u1",
    )
    assert not org_skill_allowed(owner, OrgSkillAction.FEATURE)


def test_other_member_install_only():
    other = _ctx("u2", "chat:use")
    assert org_skill_allowed(other, OrgSkillAction.INSTALL)
    assert org_skill_allowed(other, OrgSkillAction.UPGRADE)
    assert not org_skill_allowed(
        other,
        OrgSkillAction.UPDATE_VERSION,
        owner_user_id="u1",
    )
    assert not org_skill_allowed(
        other,
        OrgSkillAction.DELIST,
        owner_user_id="u1",
    )
    caps = org_skill_capabilities(
        other,
        owner_user_id="u1",
        installed=True,
        update_available=True,
    )
    assert caps["can_upgrade"] is True
    assert caps["can_uninstall"] is True
    assert caps["can_update_version"] is False
    assert caps["is_owner"] is False


def test_manage_can_feature_any():
    ops = _ctx("ops", "org_skill:manage")
    assert org_skill_allowed(ops, OrgSkillAction.FEATURE)
    assert org_skill_allowed(
        ops,
        OrgSkillAction.DELIST,
        owner_user_id="u1",
    )


def test_owner_ops_status_without_manage():
    owner = _ctx("u1", "org_skill:publish")
    ok, _ = org_skill_ops_allowed(
        owner,
        owner_user_id="u1",
        status="delisted",
    )
    assert ok
    ok2, reason = org_skill_ops_allowed(
        owner,
        owner_user_id="u1",
        featured=True,
    )
    assert not ok2
    assert "manage" in reason


def test_admin_break_glass():
    admin = _ctx("admin", admin=True)
    assert org_skill_allowed(
        admin,
        OrgSkillAction.DELETE_LISTING,
        owner_user_id="u1",
    )
    assert org_skill_allowed(admin, OrgSkillAction.FEATURE)
