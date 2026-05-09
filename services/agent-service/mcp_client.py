"""HTTP client helpers for mcp-news-server only (no NewsAPI)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def post_json(
    client: httpx.AsyncClient,
    base: str,
    path: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any] | None, int, str | None]:
    url = f"{base.rstrip('/')}{path}"
    try:
        resp = await client.post(url, json=body)
    except httpx.RequestError as exc:
        logger.warning("mcp request failed url=%s err=%s", url, type(exc).__name__)
        return None, 0, str(exc)
    try:
        data = resp.json()
    except ValueError:
        return None, resp.status_code, "Invalid JSON from mcp-news-server"
    return data, resp.status_code, None


async def mcp_search_news(
    client: httpx.AsyncClient,
    base: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any] | None, int, str | None]:
    return await post_json(client, base, "/v1/tools/search_news", body)


async def mcp_top_headlines(
    client: httpx.AsyncClient,
    base: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any] | None, int, str | None]:
    return await post_json(client, base, "/v1/tools/top_headlines", body)


def articles_from_response(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    raw = data.get("articles")
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, dict)]


def extract_sources(articles: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for art in articles[:limit]:
        url = (art.get("url") or "").strip()
        if not url:
            continue
        sources.append(
            {
                "title": art.get("title"),
                "url": url,
                "source_name": art.get("source_name"),
                "published_at": art.get("published_at"),
            }
        )
    return sources
