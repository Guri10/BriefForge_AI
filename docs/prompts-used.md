# Prompts used (BriefForge_AI)

Short log for the assessment video. These are paraphrases of intent, not full transcripts.

## Brainstorming

- Asked for help brainstorming an agentic news briefing app before coding: architecture **web → agent-service → mcp-news-server → NewsAPI**, two MVP tools (**search_news**, **top_headlines**), HTTP between services, MVP vs stretch, risks, rubric mapping, build order.

## Implementation planning

- Approved a written plan to replace placeholder **`/v1/chat`** with MCP-backed behavior and a fixed response shape (**`reply_markdown`**, **`brief`**, **`sources`**, **`trace.tool_calls`**), then executed it inline.

## Scaffold

- Asked to scaffold the monorepo: **React+Vite+TS** web, **FastAPI** agent and MCP services, health routes, placeholder **`/v1/chat`** and tool routes, Dockerfiles, **docker-compose**, **README**, **.env.example** — no LangChain or NewsAPI yet.

## MCP news server

- Asked to implement real **`mcp-news-server`** tools: **NewsAPI** client with **`NEWSAPI_API_KEY`**, normalization, **`POST /v1/tools/search_news`** and **`top_headlines`**, caps, **`request_echo`** in **`meta`**, safe errors — only under **`services/mcp-news-server`**.

## Environment and Docker

- Asked to wire **`.env.example`** (**`NEWSAPI_API_KEY`**, **`OPENAI_API_KEY`**, **`OPENAI_MODEL`**, **`VITE_AGENT_BASE_URL`**, optional URL vars), **`docker-compose`** so each service receives only its env vars, and recheck **`.env.example`** for correctness.

## Agent-service MCP integration (pre–LangChain)

- Asked to prove **agent-service → mcp-news-server** over HTTP: httpx client, keyword intent routing, structured response with trace, no NewsAPI in agent — only **`services/agent-service`**.

## LangChain tool-calling

- Approved a plan to replace keyword routing with **LangChain + OpenAI** tool calling (**`search_news`** / **`top_headlines`** tools → MCP HTTP only), strong system prompt (tools before factual claims, no invented URLs, summarize only returned articles), OpenAI failure fallback to keyword routing; implemented under **`services/agent-service`** only.
