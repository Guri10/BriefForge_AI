# BriefForge_AI

Agentic news briefing app: **web** → **agent-service** → **mcp-news-server** → NewsAPI.

## Ports

| Service           | Port (host) |
|-------------------|-------------|
| web               | 5173        |
| agent-service     | 8000        |
| mcp-news-server   | 8001        |

## Environment

Copy `.env.example` to `.env` at the repo root and replace the placeholder values. The real `.env` file is gitignored.

| Variable | Used by |
|----------|---------|
| `NEWSAPI_API_KEY` | mcp-news-server only (Docker: passed through Compose substitution) |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | agent-service only (when you wire the LLM) |
| `VITE_AGENT_BASE_URL` | web build (Vite); browser calls this base URL for the agent API |

Optional URL variables for your own scripts or documentation: `AGENT_SERVICE_URL`, `MCP_NEWS_SERVER_URL`.

**Docker Compose** reads the root `.env` file to fill `${...}` in `docker-compose.yml`. Each container only receives the variables listed under `environment:` / build `args:` for that service.

For **local terminals**, load the file before starting processes (from repo root):

```bash
set -a && source .env && set +a
```

## Prerequisites

- Node 20+ and npm (for local web dev / build)
- Python 3.12+ (for local API dev)
- Docker & Docker Compose (optional, for container run)

## Local development (no Docker)

Use three terminals from the repo root (after `set -a && source .env && set +a`, or export vars manually).

1. **mcp-news-server**

   ```bash
   cd services/mcp-news-server
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8001
   ```

2. **agent-service**

   ```bash
   cd services/agent-service
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   export MCP_NEWS_SERVER_URL=http://localhost:8001
   uvicorn main:app --reload --port 8000
   ```

3. **web**

   ```bash
   cd apps/web
   npm install
   npm run dev
   ```

   Vite reads `VITE_AGENT_BASE_URL` from `apps/web/.env.development` or `.env` in that directory. To match Docker defaults, use `VITE_AGENT_BASE_URL=http://localhost:8000`, or rely on the in-app default.

   Open http://localhost:5173 — the page fetches `GET /health` on the configured agent base URL.

**Smoke checks:** `curl http://localhost:8001/health`, `curl http://localhost:8000/health`, `curl -X POST http://localhost:8000/v1/chat -H 'Content-Type: application/json' -d '{"message":"hi"}'`, `curl -X POST http://localhost:8001/v1/tools/search_news -H 'Content-Type: application/json' -d '{"query":"ai"}'`.

## Docker Compose

Ensure `.env` exists at the repo root with `NEWSAPI_API_KEY`, `OPENAI_API_KEY`, and `OPENAI_MODEL` filled in (placeholders are fine for keys you are not using yet).

```bash
docker compose up --build
```

- UI: http://localhost:5173  
- agent-service: http://localhost:8000  
- mcp-news-server: http://localhost:8001  

The web image is built with `VITE_AGENT_BASE_URL` (default `http://localhost:8000` if unset) so the browser on your machine can reach the agent published on port 8000.

## Project layout

- `apps/web` — React + Vite + TypeScript (only calls agent-service).
- `services/agent-service` — FastAPI; placeholder `POST /v1/chat`.
- `services/mcp-news-server` — FastAPI; NewsAPI-backed tools.
- `docs` — architecture notes.

Never commit real secrets; use `.env` locally only.
