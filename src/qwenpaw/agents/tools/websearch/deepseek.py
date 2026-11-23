# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""DeepSeek Search & Fetch backends (https://api-docs.deepseek.com/guides/search)."""

from __future__ import annotations

import logging

import httpx

from .base import SearchProvider, _TIMEOUT, _post
from .credentials import read_optional_api_key

logger = logging.getLogger(__name__)

_CREDENTIAL_REF = "tool/web_search/deepseek"
_SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
_FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"


async def _provider_manager_deepseek_key() -> str:
    """Fall back to the DeepSeek LLM provider API key when tool slot is empty."""
    try:
        from ....providers.provider_manager import ProviderManager

        provider = ProviderManager.get_instance().get_provider("deepseek")
    except Exception:  # pylint: disable=broad-exception-caught
        return ""
    if provider is None:
        return ""
    return str(getattr(provider, "api_key", "") or "").strip()


async def current_agent_deepseek_key() -> str:
    """Resolve DeepSeek API key for Search/Fetch.

    Preference order:
    1. tool credential slot ``tool/web_search/deepseek``
    2. configured DeepSeek LLM provider ``api_key``
    """
    key = (await read_optional_api_key(_CREDENTIAL_REF)) or ""
    if key:
        return key
    return await _provider_manager_deepseek_key()


def _auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise ValueError(
            "DeepSeek Search/Fetch requires an API key. "
            "Set it in the web_search tool config, or configure the "
            "DeepSeek provider API key.",
        )
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


class DeepSeekProvider(SearchProvider):
    """DeepSeek in-house Search API backend."""

    name = "deepseek"

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[dict]:
        api_key = await current_agent_deepseek_key()
        count = max(1, min(int(max_results or 5), 50))
        data = await _post(
            _SEARCH_URL,
            headers=_auth_headers(api_key),
            payload={
                "query": query,
                "count": count,
                "need_content": True,
            },
        )
        results: list[dict] = []
        for item in data.get("results") or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            summary = str(item.get("summary") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            results.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "content": content or summary or snippet,
                    "snippet": snippet,
                },
            )
        return results


async def deepseek_fetch(url: str) -> str:
    """Fetch a page via DeepSeek Fetch API and return Markdown text."""
    api_key = await current_agent_deepseek_key()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _FETCH_URL,
            headers=_auth_headers(api_key),
            json={"url": url},
        )
    resp.raise_for_status()
    data = resp.json()
    title = str(data.get("title") or "").strip()
    content = str(data.get("content") or "").strip()
    if title and content:
        if content.lstrip().startswith("#"):
            return content
        return f"# {title}\n\n{content}"
    if content:
        return content
    if title:
        return f"# {title}"
    return ""


__all__ = [
    "DeepSeekProvider",
    "current_agent_deepseek_key",
    "deepseek_fetch",
]
