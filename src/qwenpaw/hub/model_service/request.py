# -*- coding: utf-8 -*-
"""Own one gateway attempt from durable admission through final cleanup."""

import asyncio
import logging
from contextlib import AsyncExitStack

import anyio
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ...utils.io_utils import run_async_to_completion, run_sync_io
from .budget import BudgetExceededError
from .protocol import validate_request

logger = logging.getLogger(__name__)


class GatewayRequest:
    """Keep reservation ownership even when its caller is cancelled."""

    def __init__(self, budgets, catalog, rbac=None):
        self.budgets = budgets
        self.catalog = catalog
        self.rbac = rbac
        self.stack = AsyncExitStack()
        self.reservation = None
        self.upstream_key = None
        self._identity = None
        self._closing = None

    @property
    def request_id(self):
        """Return the durable identity after successful admission."""
        return self.reservation[0] if self.reservation else None

    async def reserve(self, identity, body, *, admin_test=False):
        """Finish and retain admission before delivering cancellation."""
        limit = validate_request(body)
        with anyio.CancelScope(shield=True):
            await run_async_to_completion(
                self._reserve(identity, body["model"], limit, admin_test),
            )
        # Deliver an enclosing AnyIO cancellation before dispatching anything.
        await anyio.lowlevel.checkpoint()
        return self.reservation

    async def _reserve(self, identity, model_id, limit, admin_test):
        self._identity = identity
        try:
            self.reservation = await run_sync_io(
                self.budgets.reserve,
                identity,
                model_id,
                self.catalog,
                limit,
                admin_test=admin_test,
            )
            if self.rbac is not None and not admin_test:
                # Daily token gate after monthly Hub budget admission.
                request_id, model, _connection, cap = self.reservation
                reserved = int(model["input_token_limit"]) + int(cap or 0)
                try:
                    await run_sync_io(
                        self.rbac.admit_tokens,
                        identity["user_id"],
                        is_hub_admin=self.rbac.lookup_is_hub_admin(
                            identity["user_id"],
                        ),
                        reserved_tokens=reserved,
                    )
                except PermissionError:
                    await run_sync_io(
                        self.budgets.settle,
                        request_id,
                        None,
                        "daily_token_denied",
                    )
                    self.reservation = None
                    raise
        except BudgetExceededError as exc:
            raise HTTPException(403, "hub_budget_exceeded") from exc
        except PermissionError as exc:
            detail = str(exc) or "hub_model_unavailable"
            if "Token" in detail or "chat" in detail or "权限" in detail:
                raise HTTPException(403, detail) from exc
            raise HTTPException(403, "hub_model_unavailable") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    async def dispatch(self, timeout):
        """Persist dispatch before the transport can send upstream bytes."""
        with anyio.CancelScope(shield=True):
            await run_sync_io(self.budgets.dispatch, self.request_id, timeout)
        await anyio.lowlevel.checkpoint()

    async def close(self, actual=None, error=None):
        """Drain settlement and resource cleanup under either cancel model."""
        with anyio.CancelScope(shield=True):
            if self._closing is None:
                self._closing = asyncio.create_task(self._close(actual, error))
            await run_async_to_completion(self._closing)

    async def _close(self, actual, error):
        try:
            if self.request_id is not None:
                await run_sync_io(
                    self.budgets.settle,
                    self.request_id,
                    actual,
                    error,
                )
                if (
                    self.rbac is not None
                    and self._identity is not None
                    and actual is not None
                    and int(actual) > 0
                ):
                    await run_sync_io(
                        self.rbac.record_tokens,
                        self._identity["user_id"],
                        int(actual),
                    )
        except Exception:
            # Keep the ledger pending for recovery; never log request content.
            logger.exception(f"Model settlement failed: {self.request_id}")
            raise
        finally:
            await self.stack.aclose()


class GatewayStreamingResponse(StreamingResponse):
    """Retain request ownership even if sending headers or a chunk fails."""

    def __init__(self, content, attempt, **kwargs):
        super().__init__(content, **kwargs)
        self.attempt = attempt

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.attempt.close(error="stream_incomplete")
