# -*- coding: utf-8 -*-
"""Best-effort Hub authz audit helpers."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .policy import AuthzContext

logger = logging.getLogger(__name__)


class AuditRecorder(Protocol):
    def record(
        self,
        *,
        actor_user_id: str,
        actor_username: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str = "success",
        detail: dict[str, Any] | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        remote_address: str | None = None,
    ) -> None: ...


def record_authz_event(
    operations: AuditRecorder | None,
    *,
    ctx: AuthzContext,
    actor_username: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any] | None = None,
    outcome: str = "success",
) -> None:
    """Persist one management event; never raise to the request path."""
    if operations is None:
        return
    payload = dict(detail or {})
    if ctx.is_admin and "via_admin" not in payload:
        payload["via_admin"] = True
    try:
        operations.record(
            actor_user_id=ctx.user_id,
            actor_username=actor_username or ctx.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail=payload,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("authz audit not persisted (%s): %s", action, exc)
