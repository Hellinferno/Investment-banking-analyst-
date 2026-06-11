import { useState, useCallback, useEffect, useRef } from 'react'

/**
 * Provides a refresh trigger mechanism for WorldMonitor panels.
 *
 * Usage:
 *   const { refreshKey, refresh, isRefreshing, markDone } = useWMRefresh()
 *
 *   // In the panel's useEffect deps array: [refreshKey]
 *   // Call refresh() from a button to force a re-fetch.
 *   // Call markDone() once the load sequence completes.
 */
export function useWMRefresh(autoRefreshMs?: number) {
  const [refreshKey, setRefreshKey] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(() => {
    setIsRefreshing(true)
    setRefreshKey(k => k + 1)
  }, [])

  const markDone = useCallback(() => {
    setIsRefreshing(false)
  }, [])

  // Optional auto-refresh interval
  useEffect(() => {
    if (!autoRefreshMs) return
    timerRef.current = setInterval(() => {
      setRefreshKey(k => k + 1)
    }, autoRefreshMs)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefreshMs])

  return { refreshKey, refresh, isRefreshing, markDone }
}
