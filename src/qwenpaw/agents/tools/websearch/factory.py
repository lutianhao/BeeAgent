# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""Provider selection for the ``web_search`` tool."""

from __future__ import annotations

from ....app.agent_context import get_current_agent_id
from ....config.config import load_agent_config
from .anysearch import AnySearchProvider
from .base import SearchProvider
from .deepseek import DeepSeekProvider
from .firecrawl import FirecrawlProvider
from .tavily import TavilyProvider


def get_search_provider_name() -> str:
    """Return the configured ``web_search`` provider id (lowercased).

    Defaults to ``anysearch`` when unset or unreadable.
    """
    agent_id = get_current_agent_id()
    try:
        config = load_agent_config(agent_id)
        tool_cfg = (
            config.tools.builtin_tools.get("web_search")
            if config.tools
            else None
        )
        choice = (
            str(tool_cfg.config.get("provider") or "").strip().lower()
            if tool_cfg
            else ""
        )
    except Exception:
        choice = ""
    if not choice:
        return "anysearch"
    return choice


def get_search_provider() -> SearchProvider:
    """Return the active search provider from the current agent's Console
    tool configuration.

    Defaults to ``anysearch`` when unset. Unknown values raise ``ValueError``
    instead of silently routing.
    """
    choice = get_search_provider_name()
    if choice == "tavily":
        return TavilyProvider()
    if choice == "anysearch":
        return AnySearchProvider()
    if choice == "firecrawl":
        return FirecrawlProvider()
    if choice == "deepseek":
        return DeepSeekProvider()
    raise ValueError(
        f"Unknown web_search provider: {choice!r} "
        "(expected 'tavily', 'anysearch', 'firecrawl' or 'deepseek')",
    )


__all__ = [
    "SearchProvider",
    "get_search_provider",
    "get_search_provider_name",
]
