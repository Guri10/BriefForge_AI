# BriefForge_AI

**BriefForge** is a small **agentic news briefing** demo: you ask a question in the web UI, **agent-service** runs **LangChain + OpenAI** with tools that call **mcp-news-server** over HTTP, and you get a markdown answer, **sources**, and a **tool trace** for reviewers.

The browser **only** talks to **agent-service**. It never holds **`NEWSAPI_API_KEY`** or calls NewsAPI. **`mcp-news-server`** is an HTTP “news wrapper” (MCP-style boundary in the assessment): it owns the NewsAPI key, request shaping, errors, and normalized articles.

**More detail:** [docs/architecture.md](docs/architecture.md) · Prompt log for demos: [docs/prompts-used.md](docs/prompts-used.md)

---

## Quick start (Docker)

1. Copy **`.env.example`** → **`.env`** at the repo root and set real keys (or placeholders for unused services).
2. From the repo root:

```bash
docker compose up --build
```

3. Open **http://localhost:5173** (web), **http://localhost:8000** (agent), **http://localhost:8001** (news wrapper).

The web image is built with **`VITE_AGENT_BASE_URL`** (default **`http://localhost:8000`**) so your browser can reach the agent on the host.

---

## Ports

| Service | Port (host) |
|---------|-------------|
| web | 5173 |
| agent-service | 8000 |
| mcp-news-server | 8001 |

---

## Environment

| Variable | Used by |
|----------|---------|
| `NEWSAPI_API_KEY` | **mcp-news-server** only |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | **agent-service** (OpenAI + LangChain) |
| `VITE_AGENT_BASE_URL` | **web** build — browser → agent base URL |

**Compose** reads root **`.env`** and passes **only** the variables each service needs (see **`docker-compose.yml`**).

Optional for local scripts: `AGENT_SERVICE_URL`, `MCP_NEWS_SERVER_URL`.

Load env in shells when not using Docker:

```bash
set -a && source .env && set +a
```

---

## Local development (no Docker)

Three terminals, repo root (env loaded as above).

**1. mcp-news-server**

```bash
cd services/mcp-news-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

**2. agent-service**

```bash
cd services/agent-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MCP_NEWS_SERVER_URL=http://localhost:8001
uvicorn main:app --reload --port 8000
```

**3. web**

```bash
cd apps/web
npm install
npm run dev
```

Use **`apps/web/.env.development`** with `VITE_AGENT_BASE_URL=http://localhost:8000` if needed; otherwise the app defaults to that base URL.

**Smoke:** `curl -s http://localhost:8001/health` · `curl -s http://localhost:8000/health` · `curl -s -X POST http://localhost:8000/v1/chat -H 'Content-Type: application/json' -d '{"message":"Brief headline about science"}'`

---

## API overview

| Where | Method | Path | Purpose |
|-------|--------|------|---------|
| web (browser) | — | — | Calls agent **`POST /v1/chat`** only |
| agent-service | GET | `/health` | Liveness; shows MCP URL and whether OpenAI env is set |
| agent-service | POST | `/v1/chat` | Body `{"message": "<string>"}`. Returns `reply_markdown`, `brief`, `sources[]`, `trace.tool_calls[]` |
| mcp-news-server | GET | `/health` | Liveness; `newsapi_configured` flag |
| mcp-news-server | POST | `/v1/tools/search_news` | Search-style news (agent tools call this) |
| mcp-news-server | POST | `/v1/tools/top_headlines` | Headlines (agent tools call this) |

If OpenAI is misconfigured or errors, **agent-service** falls back to a **single** keyword-routed MCP call and still returns the same JSON shape (see **`trace.tool_calls[].error`**).

---

## Project layout

```
apps/web/                 # React + Vite + TypeScript UI
services/agent-service/   # FastAPI + LangChain + OpenAI
  main.py                 # HTTP routes, fallback routing
  agent_runner.py         # Tool loop, system prompt
  mcp_client.py           # httpx → mcp-news-server
  news_tools.py           # Tool schemas for the model
services/mcp-news-server/
  main.py                 # NewsAPI client, normalization, tool routes
docs/
  architecture.md
  prompts-used.md
docker-compose.yml
.env.example
```

---

## Design decisions (short)

- **mcp-news-server** isolates the NewsAPI key, HTTP quirks, and a stable **`articles` + `meta`** shape so the LLM layer does not embed provider details.
- **LangChain** exposes **`search_news`** and **`top_headlines`** as model tools; execution is **HTTP POSTs** to the wrapper—no NewsAPI calls inside **agent-service**.
- **Single-page web** with **`react-markdown`** for the agent reply keeps the demo easy to record and review.

---

## Limitations & future work

- No auth, accounts, or saved sessions.
- No streaming tokens in the UI.
- Fallback routing is keyword-based when OpenAI fails—not a second LLM.
- Rate limits and coverage depend on your **NewsAPI** plan.
- Possible next steps: streaming, conversation memory, stricter citation UI, tests/CI, production deploy notes.

---

## Prerequisites

- Node 20+ and npm · Python 3.12+ · Docker Compose (optional but recommended for one-command demos)

Never commit **`.env`** with real secrets.
