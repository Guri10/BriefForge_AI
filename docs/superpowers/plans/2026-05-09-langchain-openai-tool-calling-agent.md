# LangChain + OpenAI tool-calling for agent-service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace keyword-based `route_intent` in **agent-service** with a **LangChain + OpenAI** agent that chooses **`search_news`** or **`top_headlines`** via native tool-calling, executes each choice by **HTTP POST to mcp-news-server only**, then returns the **same** JSON contract as today: **`reply_markdown`**, **`brief`**, **`sources`**, **`trace.tool_calls`**.

**Architecture:** Keep **`httpx.AsyncClient`** in FastAPI lifespan for MCP I/O. Register **two LangChain tools** whose implementations are thin wrappers around existing **`mcp_search_news`** / **`mcp_top_headlines`** (same URLs under **`MCP_NEWS_SERVER_URL`**). Run a small **ReAct-style loop** (or **`langgraph`** prebuilt `create_react_agent` if you prefer one import): model message → if **`tool_calls`**, execute tools, append **`ToolMessage`**s with **stringified JSON** bodies from MCP → repeat until the model returns a final assistant message **without** tool calls (cap iterations, e.g. **5**). After the loop, **derive `sources`** by parsing **`articles`** from every successful MCP JSON accumulated during the run; build **`trace.tool_calls`** as **one list entry per MCP HTTP invocation** (same keys as today: **`name`**, **`mcp_path`**, **`arguments`**, **`mcp_http_status`**, **`mcp_response_meta`**, **`article_count`**, **`error`**). Set **`reply_markdown`** and **`brief`** from the **final** assistant text (split with a simple convention, e.g. first paragraph = **`brief`**, full message = **`reply_markdown`**, or ask the model in the system prompt to use a delimiter—pick one approach in Task 2 and keep it consistent).

**Tech Stack:** Python 3.12+, FastAPI, httpx (existing), **`langchain-openai`**, **`langchain-core`** (add **`langgraph`** only if you use the prebuilt agent; otherwise a **~30-line** manual loop in one module is enough and fewer deps).

---

## File map (all under `services/agent-service/`)

| File | Responsibility |
|------|----------------|
| `requirements.txt` | Add pinned-ish deps: `langchain-openai>=0.3.0`, `langchain-core>=0.3.0` (+ optional `langgraph>=0.2.0` if chosen). |
| `main.py` | FastAPI app, lifespan, **`POST /v1/chat`** orchestration: build agent, collect trace, shape response; **remove** `_PHRASE_TRIGGERS`, `_wants_top_headlines`, `_strip_top_query`, **`route_intent`** from the happy path (keep **`route_intent`** only inside fallback—see Task 3). |
| `mcp_client.py` (new) | Move **`_post_mcp`**, **`mcp_search_news`**, **`mcp_top_headlines`**, **`_articles_from_response`** here unchanged in behavior so **`main.py`** stays smaller. |
| `news_tools.py` (new) | LangChain **`@tool`** definitions **`search_news`** / **`top_headlines`** with Pydantic args matching MCP bodies (`query`, `language`, `from`, `to`, `page_size` vs `country`, `category`, `q`, `page_size`). Tool bodies call **`mcp_client`** with **`httpx.AsyncClient`** passed in at bind time (closure or small **`MCPToolContext`** dataclass). Tools return a **compact JSON string** (articles truncated for token budget if needed, e.g. first **10** titles+urls) for the model to read. |
| `agent_runner.py` (new) | **`SYSTEM_PROMPT`** constant + **`async def run_agent_turn(client, user_message) -> AgentResult`**: builds **`ChatOpenAI`** from **`OPENAI_API_KEY`** and **`OPENAI_MODEL`** (default **`gpt-4o-mini`** to match `.env.example`), **`bind_tools`**, runs the loop, returns **`final_text`**, **`list[ToolCallTrace]`** (internal), **`aggregated_articles`**. |

**Do not modify:** `services/mcp-news-server/**`, `apps/web/**`, root compose (unless you later add env—out of scope; **`OPENAI_API_KEY`** / **`OPENAI_MODEL`** already in compose for agent).

---

### Task 1: Dependencies and MCP module extraction

**Files:**
- Modify: `services/agent-service/requirements.txt`
- Create: `services/agent-service/mcp_client.py`

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:

```text
langchain-core>=0.3.0
langchain-openai>=0.3.0
```

- [ ] **Step 2: Move MCP helpers**

Create `mcp_client.py` exporting **`async def post_json(client, base, path, body) -> tuple[dict|None, int, str|None]`** (wrap current **`_post_mcp`**), **`mcp_search_news`**, **`mcp_top_headlines`**, **`articles_from_response`** (rename from **`_articles_from_response`**). Keep **`REQUEST_TIMEOUT_S`** and base URL handling in **`main.py`** lifespan only; pass **`base`** into each call.

**Verify:** `cd services/agent-service && .venv/bin/pip install -r requirements.txt && .venv/bin/python -c "import mcp_client; print('ok')"`

**Expected:** `ok` (no import error).

---

### Task 2: LangChain tools + system prompt + agent loop

**Files:**
- Create: `services/agent-service/news_tools.py`
- Create: `services/agent-service/agent_runner.py`

- [ ] **Step 1: Define `SYSTEM_PROMPT` in `agent_runner.py`**

Use a triple-quoted string including at least:

- You are BriefForge’s news assistant.
- **Use tools before making factual claims** about current events or news.
- **Never invent URLs or headlines**; only cite material present in tool results.
- **Summarize only articles returned** by tools; if tools return empty, say so clearly.
- After tools return, write a helpful answer for the user.

- [ ] **Step 2: Implement `make_news_tools(client, base)` in `news_tools.py`**

Return a list of two tools:

- **`search_news`** — args: **`query: str`**, optional **`language`**, **`from`**, **`to`**, **`page_size`** (default **10**, cap **20** before HTTP). Implementation: **`POST /v1/tools/search_news`** via **`mcp_client`**. Return **`json.dumps({...})`** of the MCP JSON (or a trimmed dict).

- **`top_headlines`** — args: optional **`country`**, **`category`**, **`q`**, **`page_size`**. Implementation: **`POST /v1/tools/top_headlines`**.

Neither tool may reference NewsAPI or any host other than **`base`**.

- [ ] **Step 3: Implement `run_agent_turn` in `agent_runner.py`**

```python
# Pseudocode — implement fully in repo
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

async def run_agent_turn(http: httpx.AsyncClient, mcp_base: str, user_message: str) -> AgentResult:
    tools = make_news_tools(http, mcp_base)
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.environ["OPENAI_API_KEY"],
        temperature=0.2,
    ).bind_tools(tools)
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_message)]
    trace_rows: list[dict] = []
    all_articles: list[dict] = []
    for _ in range(5):
        ai: AIMessage = await llm.ainvoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            break
        for tc in ai.tool_calls:
            name = tc["name"]
            args = tc["args"]
            # dispatch to mcp_client, append ToolMessage(content=json_str)
            # append trace_rows entry + extend all_articles from parsed JSON
    final = messages[-1].content if isinstance(messages[-1], AIMessage) else ""
    return AgentResult(final_text=final, tool_traces=trace_rows, articles=all_articles)
```

Use real imports: **`SystemMessage`** from **`langchain_core.messages`**. Handle **`tool_calls`** shape for your **`langchain-openai`** version (dict with **`name`**, **`args`**, **`id`**).

**Verify (requires real keys and MCP running):**

```bash
set -a && source ../../.env && set +a
cd services/agent-service
.venv/bin/python - <<'PY'
import asyncio, os, httpx
from agent_runner import run_agent_turn
async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await run_agent_turn(c, os.environ["MCP_NEWS_SERVER_URL"].rstrip("/"), "What are top US business headlines today?")
        print(r.final_text[:200])
        print(len(r.tool_traces), "tool traces")
asyncio.run(main())
PY
```

**Expected:** Printed assistant text; **`len(r.tool_traces) >= 1`**; at least one trace with **`name`** **`top_headlines`** or **`search_news`**.

---

### Task 3: Wire `POST /v1/chat` + OpenAI failure fallback

**Files:**
- Modify: `services/agent-service/main.py`

- [ ] **Step 1: Import `run_agent_turn` and `mcp_client` helpers**

In **`chat`**: on success, build:

- **`sources`** = **`extract_sources(aggregated_articles)`** (move **`extract_sources`** to **`mcp_client.py`** or keep in **`main.py`**—same logic as today).
- **`trace.tool_calls`** = list of dicts matching current schema (map from **`AgentResult.tool_traces`**).
- **`reply_markdown`** = final model string (or split **`brief`** = first line / first paragraph per Task 2 convention—document in code comment).
- **`brief`** = short plain string (either first paragraph of final text or explicit model line).

- [ ] **Step 2: Fallback when OpenAI fails**

Wrap **`run_agent_turn`** in **`try/except`** for **`Exception`** (or narrow to **`openai.*`** / **`langchain_core`** errors). On failure:

1. Log **`logger.exception("openai agent failed; keyword fallback")`**.
2. Call existing **`route_intent`** + single MCP call path (copy the minimal branch from pre-refactor **`main.py`**, or import preserved **`keyword_fallback_chat`** function in **`agent_runner.py`**).
3. Build the **same** four top-level keys; set **`trace.tool_calls[0]["error"]`** to include **`"fallback:keyword_routing"`** or similar string **plus** a short reason (no stack traces to client).

**Verify (OpenAI broken):** temporarily **`export OPENAI_API_KEY=invalid`** then:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"message":"renewable energy EU"}' | python3 -m json.tool
```

**Expected:** HTTP **200**; **`trace.tool_calls`** length **1**; **`name`** **`search_news`**; **`error`** field mentions fallback; **`sources`** may still populate if MCP works.

---

### Task 4: Response shaping parity + manual regression

**Files:**
- Modify: `services/agent-service/main.py` (or **`agent_runner.py`**) — ensure **`format_reply_markdown`** / **`format_brief`** from current **`main.py`** are either reused for fallback only or unified so OpenAI path and fallback both produce readable **`reply_markdown`** / **`brief`**.

- [ ] **Step 1: curl regression (happy path)**

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"message":"Summarize recent news about space exploration"}' | python3 -c \
"import sys,json; d=json.load(sys.stdin); assert set(d)=={'reply_markdown','brief','sources','trace'}; print(d['trace']['tool_calls'][0]['name'])"
```

**Expected:** Only the four keys; printed tool name **`search_news`** or **`top_headlines`** (model choice is valid either way if justified).

- [ ] **Step 2: Optional commit**

```bash
git add services/agent-service/
git commit -m "feat(agent-service): LangChain OpenAI tools for MCP news routing"
```

---

## Spec coverage (self-review)

| Requirement | Task |
|-------------|------|
| Only `services/agent-service` | File map |
| MCP unchanged | Stated |
| LangChain tools → MCP HTTP only | Task 2 |
| No NewsAPI in agent | Task 2 |
| Response shape unchanged | Tasks 2–3 |
| Strong system prompt | Task 2 |
| OpenAI failure fallback | Task 3 |
| No LangChain in MCP | Out of scope / unchanged |

## Placeholder scan

No TBD steps; iteration cap and env var names are explicit.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-09-langchain-openai-tool-calling-agent.md`.**

**Do not implement until the user approves this plan.**

Two execution options:

**1. Subagent-driven (recommended)** — fresh subagent per task, review between tasks (`subagent-driven-development`).

**2. Inline execution** — run tasks in this session with checkpoints (`executing-plans`).

Which approach do you want after approval?
