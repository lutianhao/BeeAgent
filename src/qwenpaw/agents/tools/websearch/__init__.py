# -*- coding: utf-8 -*-
"""Pluggable web search providers for the ``web_search`` tool.

The active provider and any provider API key are selected per-agent via
Console tool configuration (``BuiltinToolConfig.config`` for
``web_search``), not environment variables.
"""

from .anysearch import (
    AnySearchProvider,
    _current_agent_anysearch_key,
    _parse_auto_registered_credentials,
)
from .base import SearchProvider, format_search_results
from .deepseek import DeepSeekProvider, deepseek_fetch
from .firecrawl import FirecrawlProvider
from .factory import get_search_provider, get_search_provider_name
from .tavily import TavilyProvider

__all__ = [
    "SearchProvider",
    "TavilyProvider",
    "AnySearchProvider",
    "FirecrawlProvider",
    "DeepSeekProvider",
    "deepseek_fetch",
    "get_search_provider",
    "get_search_provider_name",
    "format_search_results",
    "_current_agent_anysearch_key",
    "_parse_auto_registered_credentials",
]
