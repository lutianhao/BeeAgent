# -*- coding: utf-8 -*-
"""BeeAgent organization-internal skill market."""

from .routes import org_skills_router
from .service import OrgSkillsService

__all__ = ["OrgSkillsService", "org_skills_router"]
