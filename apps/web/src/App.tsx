import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { ChatResponse } from './types'
import './App.css'

const agentBase =
  import.meta.env.VITE_AGENT_BASE_URL ?? 'http://localhost:8000'

const SAMPLE_HEADLINES =
  "Summarize today's top technology headlines"
const SAMPLE_AI_REG = 'Give me recent news about AI regulation'

function App() {
  const [agentHealth, setAgentHealth] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ChatResponse | null>(null)

  useEffect(() => {
    const url = `${agentBase.replace(/\/$/, '')}/health`
    fetch(url)
      .then((r) => r.json())
      .then((j) => setAgentHealth(JSON.stringify(j)))
      .catch(() => setAgentHealth('unreachable (start agent-service on :8000)'))
  }, [])

  async function submitChat(text: string) {
    const trimmed = text.trim()
    if (!trimmed) return

    const base = agentBase.replace(/\/$/, '')
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`${base}/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed }),
      })
      if (!res.ok) {
        const t = await res.text()
        throw new Error(t || res.statusText)
      }
      const data = (await res.json()) as ChatResponse
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>BriefForge</h1>
        <p className="tagline">
          Agentic news briefing — this UI only talks to agent-service (
          <code>/v1/chat</code>).
        </p>
      </header>

      <section className="panel" aria-label="Service boundaries">
        <h2>Architecture</h2>
        <ul className="list">
          <li>
            <strong>web</strong> → <code>{agentBase}</code>
          </li>
          <li>
            <strong>agent-service</strong> → LangChain + OpenAI; MCP over HTTP
          </li>
          <li>
            <strong>mcp-news-server</strong> → NewsAPI
          </li>
        </ul>
      </section>

      <section className="panel" aria-label="Agent health">
        <h2>agent-service /health</h2>
        <pre className="mono">{agentHealth ?? 'loading…'}</pre>
      </section>

      <section className="panel chat-panel" aria-label="Ask for a briefing">
        <h2>Ask for a briefing</h2>
        <p className="hint">
          The agent picks tools, calls the news service, then returns a briefing with
          sources and a trace you can show in a demo.
        </p>

        <div className="sample-row">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loading}
            onClick={() => void submitChat(SAMPLE_HEADLINES)}
          >
            Summarize today&apos;s top technology headlines
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loading}
            onClick={() => void submitChat(SAMPLE_AI_REG)}
          >
            Give me recent news about AI regulation
          </button>
        </div>

        <label className="sr-only" htmlFor="msg">
          Your question
        </label>
        <textarea
          id="msg"
          className="textarea"
          rows={4}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask a news or research question…"
          aria-label="Your question"
        />

        <div className="actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={loading || !message.trim()}
            onClick={() => void submitChat(message)}
          >
            {loading ? 'Running…' : 'Send to agent'}
          </button>
        </div>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {result ? (
          <div className="results">
            <section className="result-block" aria-labelledby="brief-heading">
              <h3 id="brief-heading" className="result-title">
                Brief
              </h3>
              <p className="brief">{result.brief}</p>
            </section>

            <section className="result-block" aria-labelledby="answer-heading">
              <h3 id="answer-heading" className="result-title">
                Answer
              </h3>
              <div className="markdown-body">
                <ReactMarkdown>{result.reply_markdown}</ReactMarkdown>
              </div>
            </section>

            <section className="result-block" aria-labelledby="sources-heading">
              <h3 id="sources-heading" className="result-title">
                Sources
              </h3>
              {result.sources.length === 0 ? (
                <p className="muted">No linked sources in this response.</p>
              ) : (
                <ol className="sources">
                  {result.sources.map((s) => (
                    <li key={s.url}>
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="source-link"
                      >
                        {s.title?.trim() || s.url}
                      </a>
                      {s.source_name ? (
                        <span className="muted"> · {s.source_name}</span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <section className="result-block" aria-labelledby="trace-heading">
              <h3 id="trace-heading" className="result-title">
                Tool trace
              </h3>
              <p className="muted small">
                Each row is one MCP HTTP call the agent made on your behalf.
              </p>
              <div className="table-wrap">
                <table className="trace-table">
                  <thead>
                    <tr>
                      <th>Tool</th>
                      <th>MCP path</th>
                      <th>HTTP</th>
                      <th>Articles</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trace.tool_calls.map((tc, i) => (
                      <tr key={`${tc.name}-${i}`}>
                        <td>
                          <code>{tc.name}</code>
                        </td>
                        <td>
                          <code>{tc.mcp_path}</code>
                        </td>
                        <td>{tc.mcp_http_status}</td>
                        <td>{tc.article_count}</td>
                        <td className="trace-error">
                          {tc.error ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.trace.tool_calls.map((tc, i) => (
                <details key={`d-${i}`} className="trace-details">
                  <summary>Request / meta · {tc.name}</summary>
                  <pre className="mono">
                    {JSON.stringify(
                      { arguments: tc.arguments, mcp_response_meta: tc.mcp_response_meta },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              ))}
            </section>
          </div>
        ) : null}
      </section>
    </div>
  )
}

export default App
