# Architecture (scaffold)

```text
Browser  →  agent-service  →  mcp-news-server  →  NewsAPI (later)
   ↑              ↑                    ↑
  web only    LangChain/LLM        key + HTTP + normalization
              (not wired yet)      (not wired yet)
```

- **web** must not call `mcp-news-server` or NewsAPI directly.
- **agent-service** must not call NewsAPI directly; it uses HTTP to `mcp-news-server` for tools (stub endpoints today).
- **mcp-news-server** will be the only component with `NEWSAPI_KEY`.

See root `README.md` for ports and run order.
