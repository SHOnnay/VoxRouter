import { useState, useEffect, useCallback } from 'react'
import { fetchStats, fetchHistory } from '../lib/api'

export function useStats(intervalMs = 2000) {
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([fetchStats(), fetchHistory(40)])
      setStats(s)
      setHistory(h.tasks || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, intervalMs)
    return () => clearInterval(id)
  }, [refresh, intervalMs])

  return { stats, history, error, refresh }
}
