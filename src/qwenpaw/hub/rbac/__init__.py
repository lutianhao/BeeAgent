# -*- coding: utf-8 -*-
"""BeeAgent RBAC extension for QwenPaw Hub."""

from .service import RbacService
from .routes import rbac_router

__all__ = ["RbacService", "rbac_router"]
