import { useCallback, useEffect, useState } from 'react'
import { getHealth, type HealthResponse } from '../lib/api'

type ConnectionStatus = 'checking' | 'online' | 'offline'

export function useHealth() {
  const [status, setStatus] = useState<ConnectionStatus>('checking')
  const [data, setData] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await getHealth(signal)
      setData(response)
      setStatus('online')
      setError(null)
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setStatus('offline')
      setError(reason instanceof Error ? reason.message : '无法连接后端')
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const initialCheck = window.setTimeout(() => void refresh(controller.signal), 0)
    const timer = window.setInterval(() => void refresh(), 30_000)
    return () => {
      controller.abort()
      window.clearTimeout(initialCheck)
      window.clearInterval(timer)
    }
  }, [refresh])

  return { status, data, error, refresh }
}
