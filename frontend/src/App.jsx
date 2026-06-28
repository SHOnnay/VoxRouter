import { useState, useRef, useEffect } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { submitTask, submitBatch } from './lib/api'
import { useStats } from './hooks/useStats'
import './App.css'

const DEMO_TASKS = [
  { prompt: "What is the capital of France?", task_type: "factual" },
  { prompt: "Is 17 a prime number?", task_type: "boolean" },
  { prompt: "Translate 'hello' to Spanish.", task_type: "factual" },
  { prompt: "What is 144 * 37?", task_type: "factual" },
  { prompt: "Explain the difference between TCP and UDP, covering reliability, ordering, use cases, and performance trade-offs.", task_type: "reasoning" },
  { prompt: "Write a Python function that implements binary search on a sorted list and returns the index of the target element, or -1 if not found. Include docstring and edge case handling.", task_type: "code" },
  { prompt: "Compare the architectural trade-offs between microservices and monolithic systems for a high-traffic e-commerce platform with 10M daily users.", task_type: "reasoning" },
  { prompt: "What color is the sky?", task_type: "factual" },
]

const COMPLEXITY_COLORS = {
  trivial: '#22c55e',
  simple: '#3b82f6',
  moderate: '#f59e0b',
  complex: '#f97316',
  expert: '#ef4444',
}

const ROUTE_COLORS = { local: '#22c55e', remote: '#ed1c24' }

function Badge({ label, color }) {
  return (
    <span className="badge" style={{ '--badge-color': color }}>
      {label}
    </span>
  )
}

function StatCard({ label, value, sub, accent }) {
  return (
    <div className="stat-card" style={{ '--accent': accent }}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

function RouteDecisionBadge({ route, escalated }) {
  if (route === 'local' && !escalated) return <Badge label="⚡ LOCAL" color="var(--green)" />
  if (escalated) return <Badge label="↑ ESCALATED" color="var(--amber)" />
  return <Badge label="☁ REMOTE" color="var(--amd-red)" />
}

function ComplexityBar({ score }) {
  const labels = ['', 'trivial', 'simple', 'moderate', 'complex', 'expert']
  const colors = ['', '#22c55e', '#3b82f6', '#f59e0b', '#f97316', '#ef4444']
  return (
    <div className="complexity-bar">
      {[1,2,3,4,5].map(i => (
        <div
          key={i}
          className="complexity-pip"
          style={{ background: i <= score ? colors[score] : 'var(--bg-3)' }}
        />
      ))}
      <span className="complexity-label" style={{ color: colors[score] }}>
        {labels[score]}
      </span>
    </div>
  )
}

function TaskRow({ task }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`task-row ${open ? 'task-row--open' : ''}`} onClick={() => setOpen(o => !o)}>
      <div className="task-row-header">
        <span className="task-id mono">{task.task_id}</span>
        <RouteDecisionBadge route={task.route} escalated={task.escalated} />
        <ComplexityBar score={task.complexity_score} />
        <span className="task-tokens mono">{task.tokens_used}t</span>
        <span className="task-cost mono">
          {task.cost_usd === 0 ? <span className="free">FREE</span> : `$${task.cost_usd.toFixed(5)}`}
        </span>
        <span className="task-latency mono">{task.latency_ms}ms</span>
        <span className="task-conf mono">{(task.confidence * 100).toFixed(0)}%</span>
        <span className="expand-icon">{open ? '▾' : '▸'}</span>
      </div>
      {open && (
        <div className="task-row-detail">
          <div className="detail-section">
            <div className="detail-label">PROMPT</div>
            <div className="detail-content mono">{task.prompt}</div>
          </div>
          <div className="detail-section">
            <div className="detail-label">ANSWER via {task.model_used}</div>
            <div className="detail-content mono">{task.answer}</div>
          </div>
          {task.escalation_reason && (
            <div className="detail-section escalation">
              <div className="detail-label">ESCALATION REASON</div>
              <div className="detail-content mono">{task.escalation_reason}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function App() {
  const { stats, history, refresh } = useStats(2000)
  const [prompt, setPrompt] = useState('')
  const [taskType, setTaskType] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastResult, setLastResult] = useState(null)
  const [activeTab, setActiveTab] = useState('submit')
  const [demoRunning, setDemoRunning] = useState(false)
  const textareaRef = useRef(null)

  const handleSubmit = async () => {
    if (!prompt.trim() || loading) return
    setLoading(true)
    try {
      const result = await submitTask(prompt.trim(), taskType || null)
      setLastResult(result)
      setPrompt('')
      await refresh()
    } catch (e) {
      alert('Error: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const runDemo = async () => {
    setDemoRunning(true)
    try {
      await submitBatch(DEMO_TASKS)
      await refresh()
    } catch (e) {
      alert('Demo error: ' + e.message)
    } finally {
      setDemoRunning(false)
    }
  }

  const handleKey = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSubmit()
  }

  // Chart data
  const routePieData = stats ? [
    { name: 'Local', value: stats.local_tasks },
    { name: 'Remote', value: stats.remote_tasks },
  ] : []

  const complexityBarData = stats
    ? Object.entries(stats.complexity_distribution || {}).map(([k, v]) => ({
        name: k,
        count: v,
        fill: COMPLEXITY_COLORS[k] || '#6b7591',
      }))
    : []

  const effScore = stats?.token_efficiency_score ?? 0

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-vox">VOX</span>
            <span className="logo-router">ROUTER</span>
            <span className="logo-tag">HYBRID TOKEN-EFFICIENT ROUTING AGENT</span>
          </div>
          <div className="header-meta">
            <span className="chip amd">AMD ACT II · TRACK 1</span>
            <div className="live-dot" />
          </div>
        </div>
      </header>

      {/* ── Stats Row ── */}
      <section className="stats-row">
        <StatCard
          label="Efficiency Score"
          value={`${effScore}%`}
          sub="routing accuracy"
          accent="var(--amd-red)"
        />
        <StatCard
          label="Local Route"
          value={stats ? `${stats.local_pct}%` : '—'}
          sub={stats ? `${stats.local_tasks} tasks` : ''}
          accent="var(--green)"
        />
        <StatCard
          label="Tokens Used"
          value={stats ? stats.total_tokens.toLocaleString() : '—'}
          sub="total across all tasks"
          accent="var(--blue)"
        />
        <StatCard
          label="Cost Saved"
          value={stats ? `$${stats.total_saved_usd.toFixed(4)}` : '—'}
          sub="vs always-remote"
          accent="var(--amber)"
        />
        <StatCard
          label="Avg Confidence"
          value={stats ? `${(stats.avg_confidence * 100).toFixed(1)}%` : '—'}
          sub="across all outputs"
          accent="var(--purple)"
        />
        <StatCard
          label="Avg Latency"
          value={stats ? `${stats.avg_latency_ms}ms` : '—'}
          sub="end-to-end"
          accent="var(--amd-red)"
        />
      </section>

      {/* ── Main Grid ── */}
      <main className="main-grid">
        {/* Left: Submit + Charts */}
        <div className="left-panel">
          <div className="tabs">
            <button className={`tab ${activeTab === 'submit' ? 'tab--active' : ''}`} onClick={() => setActiveTab('submit')}>Submit Task</button>
            <button className={`tab ${activeTab === 'charts' ? 'tab--active' : ''}`} onClick={() => setActiveTab('charts')}>Analytics</button>
          </div>

          {activeTab === 'submit' && (
            <div className="panel submit-panel">
              <div className="form-group">
                <label className="form-label">TASK PROMPT</label>
                <textarea
                  ref={textareaRef}
                  className="textarea mono"
                  placeholder="Enter a task for the router to classify and dispatch…"
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  onKeyDown={handleKey}
                  rows={5}
                />
                <div className="form-hint">⌘+Enter to submit</div>
              </div>

              <div className="form-group">
                <label className="form-label">TASK TYPE (optional hint)</label>
                <select className="select" value={taskType} onChange={e => setTaskType(e.target.value)}>
                  <option value="">— auto-detect —</option>
                  <option value="factual">factual</option>
                  <option value="boolean">boolean</option>
                  <option value="classification">classification</option>
                  <option value="extraction">extraction</option>
                  <option value="reasoning">reasoning</option>
                  <option value="generation">generation</option>
                  <option value="code">code</option>
                  <option value="math_proof">math_proof</option>
                </select>
              </div>

              <div className="form-actions">
                <button
                  className="btn btn-primary"
                  onClick={handleSubmit}
                  disabled={loading || !prompt.trim()}
                >
                  {loading ? <span className="spinner" /> : null}
                  {loading ? 'Routing…' : '⚡ Route Task'}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={runDemo}
                  disabled={demoRunning}
                >
                  {demoRunning ? 'Running…' : '▶ Run Demo Suite'}
                </button>
              </div>

              {lastResult && (
                <div className="result-card">
                  <div className="result-header">
                    <RouteDecisionBadge route={lastResult.route} escalated={lastResult.escalated} />
                    <ComplexityBar score={lastResult.complexity_score} />
                    <span className="result-model mono">{lastResult.model_used}</span>
                  </div>
                  <div className="result-answer mono">{lastResult.answer}</div>
                  <div className="result-meta">
                    <span>{lastResult.tokens_used} tokens</span>
                    <span>·</span>
                    <span>{lastResult.cost_usd === 0 ? 'FREE' : `$${lastResult.cost_usd.toFixed(5)}`}</span>
                    <span>·</span>
                    <span>{lastResult.latency_ms}ms</span>
                    <span>·</span>
                    <span>{(lastResult.confidence * 100).toFixed(0)}% conf</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'charts' && (
            <div className="panel charts-panel">
              <div className="chart-section">
                <div className="chart-title">ROUTE DISTRIBUTION</div>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={routePieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={75}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {routePieData.map((entry, i) => (
                        <Cell key={i} fill={ROUTE_COLORS[entry.name.toLowerCase()]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--text-0)' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pie-legend">
                  <span style={{ color: 'var(--green)' }}>■ Local ({stats?.local_tasks ?? 0})</span>
                  <span style={{ color: 'var(--amd-red)' }}>■ Remote ({stats?.remote_tasks ?? 0})</span>
                </div>
              </div>

              <div className="chart-section">
                <div className="chart-title">COMPLEXITY DISTRIBUTION</div>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={complexityBarData} barSize={24}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-2)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-2)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--text-0)' }}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {complexityBarData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="efficiency-meter">
                <div className="chart-title">TOKEN EFFICIENCY SCORE</div>
                <div className="meter-track">
                  <div className="meter-fill" style={{ width: `${effScore}%`, background: effScore > 80 ? 'var(--green)' : effScore > 50 ? 'var(--amber)' : 'var(--amd-red)' }} />
                </div>
                <div className="meter-value" style={{ color: effScore > 80 ? 'var(--green)' : effScore > 50 ? 'var(--amber)' : 'var(--amd-red)' }}>
                  {effScore}/100
                </div>
                <div className="meter-hint">Higher = better routing decisions per token</div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Live task feed */}
        <div className="right-panel">
          <div className="panel feed-panel">
            <div className="feed-header">
              <span className="feed-title">ROUTING FEED</span>
              <span className="feed-count mono">{stats?.total_tasks ?? 0} tasks</span>
            </div>
            <div className="feed-cols">
              <span>ID</span>
              <span>ROUTE</span>
              <span>COMPLEXITY</span>
              <span>TOKENS</span>
              <span>COST</span>
              <span>LAT</span>
              <span>CONF</span>
              <span />
            </div>
            <div className="feed-list">
              {history.length === 0 ? (
                <div className="feed-empty">
                  No tasks yet — submit one or run the demo suite.
                </div>
              ) : (
                history.map(t => <TaskRow key={t.task_id + t.timestamp} task={t} />)
              )}
            </div>
          </div>
        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="footer">
        <span>VoxRouter · AMD Developer Hackathon ACT II · Track 1</span>
        <span className="footer-stack mono">FastAPI · Ollama · Fireworks AI · React · Recharts</span>
      </footer>
    </div>
  )
}
