"""Agent service: LangChain + OpenAI tool-calling to mcp-news-server over HTTP only."""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_runner import run_agent_turn
from mcp_client import (
    articles_from_response,
    extract_sources,
    mcp_search_news,
    mcp_top_headlines,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 30.0

_mcp_base = os.getenv("MCP_NEWS_SERVER_URL", "http://localhost:8001").rstrip("/")

_PHRASE_TRIGGERS: tuple[str, ...] = (
    "top headlines",
    "breaking news",
    "headlines",
    "headline",
    "breaking:",
)


def _wants_top_headlines(lower: str) -> bool:
    if any(p in lower for p in _PHRASE_TRIGGERS):
        return True
    if "today" in lower:
        return True
    if "technology" in lower:
        return True
    if "business" in lower:
        return True
    if re.search(r"\btop\b", lower):
        return True
    return False


def _strip_top_query(text: str) -> str:
    q = text
    for p in sorted(_PHRASE_TRIGGERS, key=len, reverse=True):
        q = re.sub(re.escape(p), "", q, flags=re.IGNORECASE)
    for pattern in (r"\btechnology\b", r"\bbusiness\b", r"\btoday\b", r"\btop\b"):
        q = re.sub(pattern, "", q, flags=re.IGNORECASE)
    q = " ".join(q.split()).strip(" \t:-—")
    return q or "news"


def route_intent(message: str) -> tuple[str, dict[str, Any]]:
    """Keyword routing for OpenAI failure fallback only."""
    text = message.strip()
    lower = text.lower()

    if _wants_top_headlines(lower):
        q = _strip_top_query(text)
        return "top_headlines", {"q": q, "page_size": 10}

    return "search_news", {"query": text or "news", "page_size": 10}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        app.state.http = client
        yield


app = FastAPI(
    title="BriefForge Agent Service",
    description="Agent + briefing API. Calls mcp-news-server only for news data.",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


def format_brief(
    tool: str,
    article_count: int,
    http_ok: bool,
    error_hint: str | None,
) -> str:
    if error_hint:
        return error_hint
    if not http_ok:
        return f"Request to {tool} did not complete successfully."
    if article_count == 0:
        return f"No articles returned from {tool} for this query."
    return f"Retrieved {article_count} article(s) via {tool} (keyword fallback — no LLM)."


def format_reply_markdown(
    tool: str,
    articles: list[dict[str, Any]],
    http_ok: bool,
    error_hint: str | None,
) -> str:
    if error_hint:
        return f"**Error:** {error_hint}"
    if not http_ok:
        return "**Error:** The news service returned an error."
    lines = ["## Briefing", ""]
    if not articles:
        lines.append(f"_No articles from {tool}._")
        return "\n".join(lines)
    lines.append("### Sources")
    for art in articles[:15]:
        title = (art.get("title") or "Untitled").strip()
        url = (art.get("url") or "").strip()
        if url:
            lines.append(f"- [{title}]({url})")
    return "\n".join(lines)


def _one_tool_call(
    name: str,
    mcp_path: str,
    arguments: dict[str, Any],
    status: int,
    meta: dict[str, Any],
    article_count: int,
    error: str | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "mcp_path": mcp_path,
        "arguments": arguments,
        "mcp_http_status": status,
        "mcp_response_meta": meta,
        "article_count": article_count,
        "error": error,
    }


async def _keyword_fallback_response(
    client: httpx.AsyncClient,
    message: str,
    fallback_reason: str,
) -> dict[str, Any]:
    tool, payload = route_intent(message)
    if tool == "search_news":
        data, status, transport_err = await mcp_search_news(client, _mcp_base, payload)
        mcp_path = "/v1/tools/search_news"
    else:
        data, status, transport_err = await mcp_top_headlines(client, _mcp_base, payload)
        mcp_path = "/v1/tools/top_headlines"

    meta: dict[str, Any] = {}
    if isinstance(data, dict):
        maybe = data.get("meta")
        if isinstance(maybe, dict):
            meta = maybe

    if transport_err:
        err = (
            f"fallback:keyword_routing ({fallback_reason[:120]}) | mcp: {transport_err}"
        )
        return {
            "reply_markdown": format_reply_markdown(tool, [], False, transport_err),
            "brief": format_brief(tool, 0, False, transport_err),
            "sources": [],
            "trace": {
                "tool_calls": [
                    _one_tool_call(tool, mcp_path, payload, status, {}, 0, err),
                ]
            },
        }

    articles = articles_from_response(data)
    http_ok = 200 <= status < 300
    err_detail: str | None = None
    if not http_ok:
        if isinstance(data, dict) and "detail" in data:
            d = data["detail"]
            err_detail = d if isinstance(d, str) else str(d)
        else:
            err_detail = f"mcp-news-server returned HTTP {status}"

    fb = f"fallback:keyword_routing ({fallback_reason[:180]})"
    trace_error = fb + (f" | mcp: {err_detail}" if err_detail else "")

    sources = extract_sources(articles)
    brief = format_brief(tool, len(articles), http_ok, err_detail if not http_ok else None)
    reply_md = format_reply_markdown(
        tool,
        articles,
        http_ok,
        err_detail if not http_ok else None,
    )

    return {
        "reply_markdown": reply_md,
        "brief": brief,
        "sources": sources,
        "trace": {
            "tool_calls": [
                _one_tool_call(
                    tool,
                    mcp_path,
                    payload,
                    status,
                    meta,
                    len(articles),
                    trace_error,
                )
            ]
        },
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "agent-service",
        "mcp_news_server_url": _mcp_base,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
    }


@app.post("/v1/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.http

    try:
        result = await run_agent_turn(client, _mcp_base, body.message)
        return {
            "reply_markdown": result.reply_markdown,
            "brief": result.brief,
            "sources": extract_sources(result.articles),
            "trace": {"tool_calls": result.tool_calls},
        }
    except Exception as exc:
        logger.exception("openai agent failed; keyword fallback")
        reason = f"{type(exc).__name__}: {exc!s}"[:240]
        return await _keyword_fallback_response(client, body.message, reason)
