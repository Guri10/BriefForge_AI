# Agent `/v1/chat` response shape + intent rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current `/v1/chat` JSON shape (`message_echo`, nested `briefing`) with **`reply_markdown`**, **`brief`**, **`sources`**, and **`trace.tool_calls`**, while routing to **`top_headlines`** or **`search_news`** MCP endpoints via **`httpx`** only—no LangChain, no NewsAPI.

**Architecture:** Keep a single shared **`httpx.AsyncClient`** (lifespan) and **`MCP_NEWS_SERVER_URL`** base URL. Replace `route_intent()` heuristics with keyword lists that prefer **`top_headlines`** when the user message suggests headlines, “today”, or category-style topics (**technology**, **business**). After one MCP `POST`, derive **`brief`** (one short plain-text line), **`reply_markdown`** (titles + links + optional error line), **`sources`** (same normalized list you already build from article dicts), and **`trace.tool_calls`** as a one-element list describing the single HTTP tool invocation.

**Tech Stack:** Python 3.12+, FastAPI, httpx (already in `requirements.txt`).

---

## File map

| File | Action |
|------|--------|
| `services/agent-service/main.py` | Only file to edit: routing helpers, response builders, `/v1/chat` return model. |
| `services/agent-service/requirements.txt` | No change unless you add dev deps (not required). |

---

### Task 1: Intent routing (`top_headlines` vs `search_news`)

**Files:**
- Modify: `services/agent-service/main.py` (`route_intent` and related constants)

- [ ] **Step 1: Replace `route_intent` triggers**

Implement **`route_intent(message: str) -> tuple[str, dict[str, Any]]`** so that:

- **`top_headlines`** when the lowercased message matches any of:
  - **Headlines / topical:** `headline`, `headlines`, `top headlines`, `breaking news`, `breaking:`, **`top`**, **`today`**
  - **Categories:** **`technology`**, **`business`** (whole word or phrase—use word-boundary checks or explicit substring lists as long as “technology” and “business” reliably match user wording; substring match is acceptable for this demo.)

- **`search_news`** for all other non-empty messages (default `query` to stripped text or `"news"` if empty—`ChatRequest` already enforces `min_length=1`).

For **`top_headlines`**, build `{"q": <cleaned query>, "page_size": 10}` after stripping trigger tokens (reuse **longest-first** removal from current code to avoid partial word bugs). If nothing remains, use **`q: "news"`**. Optionally pass **`category`** when the message is clearly just `technology` or `business` (maps to NewsAPI’s category enum on the MCP side)—**YAGNI:** a single **`q`** field is enough for this step unless you want `category=technology` with empty `q`; simplest is **`q`** = user text or keyword.

**Run:** `cd services/agent-service && .venv/bin/python -c "import main; print(main.route_intent('technology news')); print(main.route_intent('climate deal'))"`

**Expected:**

```text
('top_headlines', {'q': ...})
('search_news', {'query': 'climate deal', 'page_size': 10})
```

---

### Task 2: `reply_markdown`, `brief`, `sources`, `trace.tool_calls`

**Files:**
- Modify: `services/agent-service/main.py`

- [ ] **Step 1: Add `format_reply_markdown(tool, articles, error_hint | None) -> str`**

- If **`error_hint`**: return a short markdown paragraph, e.g. `**Error:** {error_hint}`.
- Else: first line **`## Briefing`** or similar, then a bullet list: `- [title](url)` for each article with a non-empty **`url`** (cap at 10–15 for readability, matching current `sources` cap).

- [ ] **Step 2: Add `format_brief(tool, article_count, error_hint | None) -> str`**

- One or two sentences, plain text: either the error, or “Retrieved N article(s) via {tool}.” / “No articles returned.”

- [ ] **Step 3: Reuse or rename `build_briefing` sources extraction**

- Keep a single function that returns **`list[dict]`** with **`title`**, **`url`**, **`source_name`**, **`published_at`** (unchanged fields). Expose as **`sources`** at the top level (not nested under `briefing`).

- [ ] **Step 4: Build `trace.tool_calls`**

After the MCP call, set:

```python
trace = {
    "tool_calls": [
        {
            "name": "search_news" | "top_headlines",
            "mcp_path": "/v1/tools/search_news" | "/v1/tools/top_headlines",
            "arguments": payload,  # same dict sent to MCP
            "mcp_http_status": status,
            "mcp_response_meta": meta,  # from MCP JSON .meta or {}
            "article_count": len(articles),
            "error": transport_err or (err_detail if not http_ok else None),
        }
    ]
}
```

Use **`None`** for **`error`** on full success.

---

### Task 3: Wire `POST /v1/chat` response and remove old keys

**Files:**
- Modify: `services/agent-service/main.py` (`chat` handler)

- [ ] **Step 1: Return only the new shape**

```python
return {
    "reply_markdown": ...,
    "brief": ...,
    "sources": ...,
    "trace": trace,  # includes tool_calls
}
```

Remove top-level **`message_echo`**, **`briefing`**, and the old flat **`trace`** keys (**`intent`**, **`mcp_path`** at top level, etc.) so the contract matches this plan.

- [ ] **Step 2: Manual integration test (mcp + agent running)**

Terminal A (repo root, env loaded):

```bash
set -a && source .env && set +a
cd services/mcp-news-server && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
```

Terminal B:

```bash
set -a && source .env && set +a
cd services/agent-service && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Terminal C:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"today technology headlines"}' | python3 -m json.tool
```

**Expected (shape):**

- Top-level keys: **`reply_markdown`**, **`brief`**, **`sources`**, **`trace`**
- **`trace.tool_calls`** length **1**
- **`trace.tool_calls[0].name`** == **`"top_headlines"`**
- **`sources`** is a **list** of objects with **`url`** strings when NewsAPI returns articles

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"renewable energy policy EU"}' | python3 -m json.tool
```

**Expected:** **`trace.tool_calls[0].name`** == **`"search_news"`**

---

## Spec coverage (self-review)

| Requirement | Task |
|-------------|------|
| Only `services/agent-service` | File map |
| HTTP client + `MCP_NEWS_SERVER_URL` | Already present; Task 3 keeps lifespan/`_post_mcp` |
| `top_headlines` when headlines/top/today/technology/business | Task 1 |
| `search_news` otherwise | Task 1 |
| `reply_markdown`, `brief`, `sources`, `trace.tool_calls` | Tasks 2–3 |
| No NewsAPI / no LangChain | Architecture; no new deps |
| Prove MCP HTTP works | Task 3 curl |

## Placeholder scan

No TBDs; error handling is explicit (`error` field in `tool_calls`).

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-09-agent-service-chat-response-shape.md`.**

**Do not start implementation until the user approves this plan.**

After approval, two execution options:

**1. Subagent-driven (recommended)** — one subagent per task, review between tasks (skill: `subagent-driven-development`).

**2. Inline execution** — run tasks in this session with checkpoints (skill: `executing-plans`).

Which approach do you want?
