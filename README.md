# BriefForge_AI

Agentic news briefing app: **web** → **agent-service** → **mcp-news-server** → NewsAPI (NewsAPI integration not in this scaffold).

## Ports

| Service           | Port (host) |
|-------------------|-------------|
| web               | 5173        |
| agent-service     | 8000        |
| mcp-news-server   | 8001        |

## Prerequisites

- Node 20+ and npm (for local web dev / build)
- Python 3.12+ (for local API dev)
- Docker & Docker Compose (optional, for container run)

## Local development (no Docker)

Use three terminals from the repo root.

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

   Optional: create `apps/web/.env.development` with `VITE_AGENT_SERVICE_URL=http://localhost:8000` if you need a non-default agent URL.

   Open http://localhost:5173 — the page fetches `GET /health` from the agent (default base URL `http://localhost:8000`).

**Smoke checks:** `curl http://localhost:8001/health`, `curl http://localhost:8000/health`, placeholders `curl -X POST http://localhost:8000/v1/chat -H 'Content-Type: application/json' -d '{"message":"hi"}'`, `curl -X POST http://localhost:8001/v1/tools/search_news -H 'Content-Type: application/json' -d '{"query":"ai"}'`.

## Docker Compose

From the repo root:

```bash
docker compose up --build
```

- UI: http://localhost:5173  
- agent-service: http://localhost:8000  
- mcp-news-server: http://localhost:8001  

The web image is built with `VITE_AGENT_SERVICE_URL=http://localhost:8000` so the browser (on your machine) can reach the agent published on port 8000.

## Project layout

- `apps/web` — React + Vite + TypeScript (only calls agent-service).
- `services/agent-service` — FastAPI; placeholder `POST /v1/chat`.
- `services/mcp-news-server` — FastAPI; placeholder news tools; will own NewsAPI later.
- `docs` — architecture notes.

Copy `.env.example` to `.env` when you add API keys; never commit real secrets.
