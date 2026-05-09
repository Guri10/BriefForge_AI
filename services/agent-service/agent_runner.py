"""LangChain + OpenAI tool loop; MCP HTTP execution only."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from mcp_client import articles_from_response, mcp_search_news, mcp_top_headlines
from news_tools import make_news_tools

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 5

SYSTEM_PROMPT = """You are BriefForge's news assistant.

Rules:
- Use tools (search_news or top_headlines) before making factual claims about current events or news.
- Never invent URLs or headlines; only cite material returned by tools.
- Summarize only articles that appear in tool results. If tools return no articles, say that clearly.
- After you have tool results, answer the user in markdown.

Format your final reply exactly:
- First line must be: BRIEF: <one plain-language sentence for the user>
- Then one blank line
- Then your full markdown answer (use headings and bullets; link only to URLs that appeared in tool results).
"""


def _clamp_page_size(ps: int | None) -> int:
    if ps is None:
        return 10
    return max(1, min(20, int(ps)))


def _tool_trace_row(
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


def _normalize_tool_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def split_brief_and_reply(final_text: str) -> tuple[str, str]:
    """Parse BRIEF: line + body; fallback to first paragraph as brief."""
    t = (final_text or "").strip()
    if not t:
        return "No response.", ""
    upper_start = t.upper()
    if upper_start.startswith("BRIEF:"):
        rest = t[6:].lstrip()
        if "\n\n" in rest:
            brief_line, reply = rest.split("\n\n", 1)
            return brief_line.strip(), reply.strip()
        first_nl = rest.find("\n")
        if first_nl != -1:
            return rest[:first_nl].strip(), rest[first_nl:].strip()
        return rest.strip(), rest.strip()
    if "\n\n" in t:
        a, b = t.split("\n\n", 1)
        return a.strip(), b.strip()
    line = t.split("\n", 1)[0].strip()
    return line, t


@dataclass
class AgentRunResult:
    brief: str
    reply_markdown: str
    tool_calls: list[dict[str, Any]]
    articles: list[dict[str, Any]]


async def run_agent_turn(
    http: httpx.AsyncClient,
    mcp_base: str,
    user_message: str,
) -> AgentRunResult:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    tools = make_news_tools()
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0.2,
    ).bind_tools(tools)

    messages: list[Any] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    trace_rows: list[dict[str, Any]] = []
    aggregated: list[dict[str, Any]] = []

    for _ in range(MAX_AGENT_ITERATIONS):
        ai: AIMessage = await llm.ainvoke(messages)
        messages.append(ai)

        tcalls = getattr(ai, "tool_calls", None) or []
        if not tcalls:
            break

        for tc in tcalls:
            if isinstance(tc, dict):
                name = tc.get("name") or ""
                tid = tc.get("id") or ""
                raw_args = tc.get("args")
            else:
                name = getattr(tc, "name", "") or ""
                tid = getattr(tc, "id", "") or ""
                raw_args = getattr(tc, "args", {})

            args = _normalize_tool_args(raw_args)
            meta: dict[str, Any] = {}
            data: dict[str, Any] | None = None
            status = 0
            transport_err: str | None = None

            if name == "search_news":
                mcp_path = "/v1/tools/search_news"
                body = {
                    "query": args.get("query") or "news",
                    "language": args.get("language"),
                    "from": args.get("from") or args.get("from_"),
                    "to": args.get("to"),
                    "page_size": _clamp_page_size(
                        args.get("page_size") if args.get("page_size") is not None else None
                    ),
                }
                data, status, transport_err = await mcp_search_news(http, mcp_base, body)
            elif name == "top_headlines":
                mcp_path = "/v1/tools/top_headlines"
                body = {
                    "country": args.get("country"),
                    "category": args.get("category"),
                    "q": args.get("q"),
                    "page_size": _clamp_page_size(
                        args.get("page_size") if args.get("page_size") is not None else None
                    ),
                }
                data, status, transport_err = await mcp_top_headlines(http, mcp_base, body)
            else:
                mcp_path = "/unknown"
                body = args
                transport_err = f"Unknown tool: {name}"

            if transport_err:
                payload = {"error": transport_err}
                trace_rows.append(
                    _tool_trace_row(
                        name or "unknown",
                        mcp_path,
                        body,
                        status,
                        {},
                        0,
                        transport_err,
                    )
                )
                messages.append(
                    ToolMessage(
                        content=json.dumps(payload),
                        tool_call_id=tid or "call",
                    )
                )
                continue

            if isinstance(data, dict):
                maybe = data.get("meta")
                if isinstance(maybe, dict):
                    meta = maybe

            arts = articles_from_response(data)
            aggregated.extend(arts)
            http_ok = 200 <= status < 300
            err_detail: str | None = None
            if not http_ok and isinstance(data, dict) and "detail" in data:
                d = data["detail"]
                err_detail = d if isinstance(d, str) else str(d)
            elif not http_ok:
                err_detail = f"mcp-news-server returned HTTP {status}"

            compact = {
                "articles": arts[:12],
                "meta": meta,
                "http_ok": http_ok,
                "error": err_detail,
            }
            trace_rows.append(
                _tool_trace_row(
                    name,
                    mcp_path,
                    body,
                    status,
                    meta,
                    len(arts),
                    err_detail if not http_ok else None,
                )
            )
            messages.append(
                ToolMessage(
                    content=json.dumps(compact, default=str),
                    tool_call_id=tid or "call",
                )
            )

    def _aimessage_text(msg: AIMessage) -> str:
        c = msg.content
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            parts: list[str] = []
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        return ""

    final_text = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            tcalls = getattr(m, "tool_calls", None) or []
            if not tcalls:
                final_text = _aimessage_text(m)
                break

    brief, reply_md = split_brief_and_reply(final_text)
    if not reply_md:
        reply_md = final_text.strip() or brief

    return AgentRunResult(
        brief=brief,
        reply_markdown=reply_md,
        tool_calls=trace_rows,
        articles=aggregated,
    )
