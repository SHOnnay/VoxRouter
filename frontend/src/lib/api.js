const BASE = import.meta.env.VITE_API_URL || '/api'

export async function submitTask(prompt, taskType = null, forceLocal = false, forceRemote = false) {
  const res = await fetch(`${BASE}/task`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, task_type: taskType, force_local: forceLocal, force_remote: forceRemote }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Task failed')
  }
  return res.json()
}

export async function submitBatch(tasks) {
  const res = await fetch(`${BASE}/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tasks }),
  })
  if (!res.ok) throw new Error('Batch failed')
  return res.json()
}

export async function fetchStats() {
  const res = await fetch(`${BASE}/stats`)
  if (!res.ok) throw new Error('Stats unavailable')
  return res.json()
}

export async function fetchHistory(limit = 40) {
  const res = await fetch(`${BASE}/history?limit=${limit}`)
  if (!res.ok) throw new Error('History unavailable')
  return res.json()
}
