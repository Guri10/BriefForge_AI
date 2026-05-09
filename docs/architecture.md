# Architecture

Read this with the root **[README.md](../README.md)** (ports and run commands).

## Request path

```text
Browser (apps/web)
    │  GET /health, POST /v1/chat   ← VITE_AGENT_BASE_URL → agent only
    ▼
agent-service (FastAPI + LangChain + OpenAI)
    │  POST /v1/tools/search_news
    │  POST /v1/tools/top_headlines   ← MCP_NEWS_SERVER_URL (HTTP)
    ▼
mcp-news-server (FastAPI)
    │  HTTPS to newsapi.org
    ▼
NewsAPI
```

Nothing in **`apps/web`** or **`services/agent-service`** calls **`newsapi.org`**. Only **`mcp-news-server`** uses **`NEWSAPI_API_KEY`**.

## Why mcp-news-server exists

NewsAPI is a third-party HTTP API with its own auth, limits, and response shape. **`mcp-news-server`** keeps that complexity in **one** place: env key, error mapping, **`page_size`** caps, and **`articles` + `meta`** (including **`request_echo`**) so **agent-service** always speaks a small, stable JSON contract. That matches the assessment idea of an **MCP-style wrapper** even though transport here is **HTTP**, not stdio.

## LangChain and OpenAI

**agent-service** builds a **`ChatOpenAI`** model with **`bind_tools`** over two tools—**`search_news`** and **`top_headlines`**—defined in **`news_tools.py`**. The model may emit tool calls; **`agent_runner.py`** executes each call by **POSTing** to **`mcp-news-server`**, appends **`ToolMessage`** payloads (JSON from MCP) to the thread, and loops until the model returns a final text answer (bounded iterations).

The system prompt tells the model to **use tools before factual claims**, **not invent URLs or headlines**, and **summarize only returned articles**. If OpenAI is missing or errors, **`main.py`** catches the failure and performs a **single** keyword-routed MCP call so the UI still gets the same response shape.

## Trust boundaries

| Secret / asset | Lives in |
|----------------|----------|
| `NEWSAPI_API_KEY` | **mcp-news-server** only |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | **agent-service** only |
| Public UI | **apps/web** — no provider keys in the bundle |

## `/v1/chat` response shape (agent → browser)

Illustrative keys only:

```json
{
  "brief": "One-line summary for the UI.",
  "reply_markdown": "## …\n\nMarkdown body…",
  "sources": [
    { "title": "…", "url": "https://…", "source_name": "…", "published_at": "…" }
  ],
  "trace": {
    "tool_calls": [
      {
        "name": "search_news",
        "mcp_path": "/v1/tools/search_news",
        "arguments": { "query": "…", "page_size": 10 },
        "mcp_http_status": 200,
        "mcp_response_meta": { "provider": "newsapi", "fetched_at": "…", "request_echo": {} },
        "article_count": 10,
        "error": null
      }
    ]
  }
}
```

When OpenAI fails and fallback runs, **`trace.tool_calls[0].error`** includes **`fallback:keyword_routing`** so reviewers can see the path taken.
