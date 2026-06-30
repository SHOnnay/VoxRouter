import { useState, useRef, useEffect } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { submitTask, submitBatch, startBenchmark, fetchBenchmark, fetchBenchmarkList } from './lib/api'
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

function BenchmarkPanel() {
  const [tier, setTier] = useState('all')
  const [runId, setRunId] = useState(null)
  const [report, setReport] = useState(null)
  const [progress, setProgress] = useState([])
  const [running, setRunning] = useState(false)
  const [history, setHistory] = useState([])

  useEffect(() => {
    fetchBenchmarkList().then(d => setHistory(d.runs || [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (!runId) return
    const interval = setInterval(async () => {
      try {
        const data = await fetchBenchmark(runId)
        setProgress(data.progress || [])
        if (data.status === 'complete' || data.status === 'error') {
          setReport(data)
          setRunning(false)
          setHistory(prev => [{ run_id: runId, status: data.status, voxrouter_score: data.voxrouter_score, accuracy_pct: data.accuracy_pct, token_savings_pct: data.token_savings_pct, total_tasks: data.total_tasks }, ...prev])
          clearInterval(interval)
        }
      } catch {}
    }, 800)
    return () => clearInterval(interval)
  }, [runId])

  const handleRun = async () => {
    setRunning(true)
    setReport(null)
    setProgress([])
    try {
      const data = await startBenchmark(tier)
      setRunId(data.run_id)
    } catch (e) {
      alert('Error: ' + e.message)
      setRunning(false)
    }
  }

  const scoreColor = (s) => s >= 80 ? 'var(--green)' : s >= 50 ? 'var(--amber)' : 'var(--amd-red)'
  const tiers = ['all', 'trivial', 'simple', 'moderate', 'complex', 'expert']

  return (
    <div className="panel benchmark-panel">
      <div className="benchmark-header">
        <div>
          <div className="chart-title">VOXROUTER BENCHMARK</div>
          <div className="benchmark-sub">50-task eval suite · accuracy + token efficiency</div>
        </div>
        <div className="benchmark-controls">
          <select className="select select-sm" value={tier} onChange={e => setTier(e.target.value)} disabled={running}>
            {tiers.map(t => <option key={t} value={t}>{t === 'all' ? 'All 50 tasks' : `${t} (10 tasks)`}</option>)}
          </select>
          <button className="btn btn-primary btn-sm" onClick={handleRun} disabled={running}>
            {running ? <span className="spinner" /> : '▶'}
            {running ? ' Running…' : ' Run Benchmark'}
          </button>
        </div>
      </div>

      {/* Score display */}
      {report && report.status === 'complete' && (
        <div className="benchmark-score-row">
          <div className="score-main">
            <div className="score-label">VOXROUTER SCORE</div>
            <div className="score-value" style={{ color: scoreColor(report.voxrouter_score) }}>
              {report.voxrouter_score}
            </div>
            <div className="score-hint">out of 100</div>
            {report.demo_mode && (
              <div className="demo-badge">⚠ DEMO MODE</div>
            )}
          </div>
          <div className="score-breakdown">
            <div className="score-item">
              <span className="score-item-label">Accuracy</span>
              <span className="score-item-value mono" style={{ color: report.demo_mode && report.scored_tasks === 0 ? 'var(--text-2)' : scoreColor(report.accuracy_pct) }}>
                {report.demo_mode && report.scored_tasks === 0 ? 'N/A' : `${report.accuracy_pct}%`}
              </span>
              {report.demo_mode && report.scored_tasks > 0 && (
                <span style={{ fontSize: 10, color: 'var(--text-2)' }}>{report.scored_tasks} real</span>
              )}
            </div>
            <div className="score-item">
              <span className="score-item-label">Routing</span>
              <span className="score-item-value mono" style={{ color: scoreColor(report.routing_pct) }}>{report.routing_pct}%</span>
            </div>
            <div className="score-item">
              <span className="score-item-label">Token Savings</span>
              <span className="score-item-value mono" style={{ color: scoreColor(report.token_savings_pct) }}>{report.token_savings_pct}%</span>
            </div>
            <div className="score-item">
              <span className="score-item-label">Local Tasks</span>
              <span className="score-item-value mono">{report.local_tasks}/{report.total_tasks}</span>
            </div>
            <div className="score-item">
              <span className="score-item-label">Tokens Saved</span>
              <span className="score-item-value mono" style={{ color: 'var(--green)' }}>{report.tokens_saved?.toLocaleString()}</span>
            </div>
            <div className="score-item">
              <span className="score-item-label">Time</span>
              <span className="score-item-value mono">{report.elapsed_seconds}s</span>
            </div>
          </div>
        </div>
      )}

      {/* Live progress */}
      {running && (
        <div className="benchmark-progress">
          <div className="progress-header">
            <span className="chart-title">RUNNING…</span>
            <span className="mono" style={{ fontSize: 12, color: 'var(--text-2)' }}>{progress.length} completed</span>
          </div>
          <div className="progress-tasks">
            {[...progress].reverse().slice(0, 6).map((t, i) => (
              <div key={i} className="progress-task">
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-2)' }}>{t.id}</span>
                <Badge label={t.route === 'local' ? '⚡ LOCAL' : '☁ REMOTE'} color={t.route === 'local' ? 'var(--green)' : 'var(--amd-red)'} />
                <span style={{ fontSize: 11, color: t.answer_correct ? 'var(--green)' : 'var(--amd-red)' }}>
                  {t.answer_correct ? '✓ correct' : '✗ wrong'}
                </span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 'auto' }}>{t.tier}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tier breakdown */}
      {report?.tier_breakdown && (
        <div className="tier-breakdown">
          <div className="chart-title" style={{ marginBottom: 8 }}>TIER BREAKDOWN</div>
          {Object.entries(report.tier_breakdown).map(([tier, data]) => (
            <div key={tier} className="tier-row">
              <span className="tier-name" style={{ color: COMPLEXITY_COLORS[tier] }}>{tier}</span>
              <div className="tier-bar-track">
                <div className="tier-bar-fill" style={{
                  width: data.accuracy_pct != null ? `${data.accuracy_pct}%` : `${data.routing_pct}%`,
                  background: data.accuracy_pct != null ? COMPLEXITY_COLORS[tier] : 'var(--text-2)'
                }} />
              </div>
              <span className="mono" style={{ fontSize: 11, color: 'var(--text-1)', minWidth: 40 }}>
                {data.accuracy_pct != null ? `${data.accuracy_pct}%` : `${data.routing_pct}% R`}
              </span>
              <span className="mono" style={{ fontSize: 11, color: 'var(--text-2)' }}>{data.avg_tokens}t avg</span>
              {data.demo_tasks > 0 && (
                <span style={{ fontSize: 10, color: 'var(--amber)' }}>demo</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Run history */}
      {history.length > 0 && (
        <div className="benchmark-history">
          <div className="chart-title" style={{ marginBottom: 8 }}>RUN HISTORY</div>
          {history.slice(0, 5).map((run) => (
            <div key={run.run_id} className="history-row" onClick={async () => {
              try {
                const data = await fetchBenchmark(run.run_id)
                setReport({ ...data, status: 'complete' })
              } catch {}
            }}>
              <span className="mono" style={{ fontSize: 11, color: 'var(--text-2)' }}>{run.run_id}</span>
              <span style={{ fontSize: 11, color: run.status === 'complete' ? 'var(--green)' : 'var(--amber)' }}>{run.status}</span>
              {run.voxrouter_score != null && (
                <span className="mono" style={{ fontSize: 12, color: scoreColor(run.voxrouter_score), fontWeight: 700 }}>
                  {run.voxrouter_score}/100
                </span>
              )}
              <span className="mono" style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 'auto' }}>{run.total_tasks} tasks</span>
            </div>
          ))}
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
            <button className={`tab ${activeTab === 'benchmark' ? 'tab--active' : ''}`} onClick={() => setActiveTab('benchmark')}>Benchmark</button>
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

          {activeTab === 'benchmark' && (
            <BenchmarkPanel />
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
        <span className="footer-stack mono">FastAPI · Ollama · Fireworks AI · Gemini 2.5 Flash · React · Recharts</span>
      </footer>
    </div>
  )
}
