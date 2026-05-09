import { useEffect, useState } from 'react'
import './App.css'

const agentBase =
  import.meta.env.VITE_AGENT_SERVICE_URL ?? 'http://localhost:8000'

function App() {
  const [agentHealth, setAgentHealth] = useState<string | null>(null)

  useEffect(() => {
    const url = `${agentBase.replace(/\/$/, '')}/health`
    fetch(url)
      .then((r) => r.json())
      .then((j) => setAgentHealth(JSON.stringify(j)))
      .catch(() => setAgentHealth('unreachable (start agent-service on :8000)'))
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>BriefForge</h1>
        <p className="tagline">Agentic news briefing — UI talks only to agent-service.</p>
      </header>

      <section className="panel" aria-label="Service boundaries">
        <h2>Boundaries</h2>
        <ul className="list">
          <li>
            <strong>web</strong> → <code>{agentBase}</code> only
          </li>
          <li>
            <strong>agent-service</strong> → LangChain + OpenAI (later); HTTP to mcp-news-server
          </li>
          <li>
            <strong>mcp-news-server</strong> → NewsAPI (later)
          </li>
        </ul>
      </section>

      <section className="panel" aria-label="Agent health check">
        <h2>agent-service /health</h2>
        <pre className="mono">{agentHealth ?? 'loading…'}</pre>
      </section>
    </div>
  )
}

export default App
