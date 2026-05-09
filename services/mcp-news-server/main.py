"""News wrapper HTTP API. Owns NewsAPI access and normalized article payloads."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2"
MAX_PAGE_SIZE = 20
DEFAULT_PAGE_SIZE = 10
REQUEST_TIMEOUT_S = 30.0


def _api_key() -> str | None:
    v = os.environ.get("NEWSAPI_API_KEY", "").strip()
    return v or None


def clamp_page_size(n: int | None) -> int:
    if n is None:
        return DEFAULT_PAGE_SIZE
    if n < 1:
        return 1
    return min(n, MAX_PAGE_SIZE)


def normalize_article(raw: dict[str, Any]) -> dict[str, Any]:
    src = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    sid = src.get("id")
    if sid in ("", "null", None):
        sid = None
    title = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    desc = raw.get("description")
    if desc is not None and isinstance(desc, str):
        desc = desc.strip() or None
    return {
        "id": sid,
        "title": title,
        "description": desc,
        "url": url,
        "source_name": src.get("name"),
        "published_at": raw.get("publishedAt"),
        "image_url": raw.get("urlToImage"),
    }


def _strip_secrets_from_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k != "apiKey"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        app.state.http = client
        yield


app = FastAPI(
    title="BriefForge MCP News Server",
    description="HTTP layer for news tools. Only this service calls NewsAPI.",
    version="0.2.0",
    lifespan=lifespan,
)


class SearchNewsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(min_length=1)
    language: str | None = None
    from_: str | None = Field(None, alias="from")
    to: str | None = None
    page_size: int | None = None


class TopHeadlinesRequest(BaseModel):
    country: str | None = None
    category: str | None = None
    q: str | None = None
    page_size: int | None = None


def _require_key() -> str:
    key = _api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="News provider is not configured (missing NEWSAPI_API_KEY).",
        )
    return key


def _meta(
    request_echo: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": "newsapi",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "request_echo": request_echo,
    }


async def _call_newsapi(
    client: httpx.AsyncClient,
    rel_path: str,
    query_params: dict[str, Any],
) -> list[dict[str, Any]]:
    key = _require_key()
    params = {k: v for k, v in query_params.items() if v is not None and v != ""}
    params["apiKey"] = key
    url = f"{NEWSAPI_BASE}/{rel_path.lstrip('/')}"
    safe_log = _strip_secrets_from_params(params)
    logger.info("newsapi request path=%s params=%s", rel_path, safe_log)

    try:
        resp = await client.get(url, params=params)
    except httpx.TimeoutException:
        logger.warning("newsapi timeout path=%s", rel_path)
        raise HTTPException(
            status_code=504,
            detail="The news provider did not respond in time.",
        ) from None
    except httpx.RequestError as e:
        logger.warning("newsapi transport error: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail="Could not reach the news provider.",
        ) from None

    try:
        data = resp.json()
    except ValueError:
        logger.warning("newsapi non-json response status=%s", resp.status_code)
        raise HTTPException(
            status_code=502,
            detail="The news provider returned an unexpected response.",
        ) from None

    if resp.status_code == 429:
        raise HTTPException(
            status_code=503,
            detail="News rate limit reached. Try again shortly.",
        )

    if data.get("status") == "error":
        code = data.get("code") or ""
        msg = (data.get("message") or "").strip()
        logger.warning("newsapi error status=error code=%s", code)
        safe_detail = "The news provider rejected the request."
        if msg and "apikey" not in msg.lower():
            safe_detail = f"News provider error: {msg}"
        raise HTTPException(status_code=502, detail=safe_detail)

    if resp.status_code >= 400:
        logger.warning("newsapi http error status=%s", resp.status_code)
        raise HTTPException(
            status_code=502,
            detail="The news provider returned an error.",
        )

    articles = data.get("articles")
    if not isinstance(articles, list):
        return []
    return [a for a in articles if isinstance(a, dict)]


def _resolve_top_headlines(
    body: TopHeadlinesRequest,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (newsapi_params, flat_echo_including_defaults)."""
    country = body.country
    category = body.category
    q_raw = (body.q or "").strip()
    q = q_raw or None

    if country is None and category is None and q is None:
        country = "us"
    elif country is None and category is not None:
        country = "us"

    params: dict[str, Any] = {
        "country": country,
        "category": category,
        "q": q,
    }
    echo = body.model_dump()
    echo["page_size"] = clamp_page_size(body.page_size)
    echo["country"] = country
    echo["category"] = category
    echo["q"] = q
    return params, echo


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mcp-news-server",
        "newsapi_configured": _api_key() is not None,
    }


@app.post("/v1/tools/search_news")
async def search_news(body: SearchNewsRequest) -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.http
    ps = clamp_page_size(body.page_size)
    params: dict[str, Any] = {
        "q": body.query.strip(),
        "language": body.language,
        "from": body.from_,
        "to": body.to,
        "pageSize": ps,
    }
    raw_list = await _call_newsapi(client, "everything", params)
    articles = [normalize_article(a) for a in raw_list]

    echo = body.model_dump(by_alias=True)
    echo["page_size"] = ps

    return {
        "articles": articles,
        "meta": _meta(echo),
    }


@app.post("/v1/tools/top_headlines")
async def top_headlines(body: TopHeadlinesRequest) -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.http
    ps = clamp_page_size(body.page_size)
    resolved, echo = _resolve_top_headlines(body)
    resolved["pageSize"] = ps

    raw_list = await _call_newsapi(client, "top-headlines", resolved)
    articles = [normalize_article(a) for a in raw_list]

    echo["page_size"] = ps

    return {
        "articles": articles,
        "meta": _meta(echo),
    }
