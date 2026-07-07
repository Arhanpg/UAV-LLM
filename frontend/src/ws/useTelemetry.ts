import { useEffect, useRef } from 'react'
import { useMission } from '../store/missionStore'
import type { TelemetryEvent } from '../api/types'

// Subscribe to the backend glass-box telemetry stream for a session. Reconnects
// when the session id changes; buffered history is replayed on connect.
export function useTelemetry(sessionId: string | null | undefined) {
  const pushEvent = useMission((s) => s.pushEvent)
  const clearEvents = useMission((s) => s.clearEvents)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!sessionId) return
    clearEvents()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/ws/mission/${sessionId}`
    const ws = new WebSocket(url)
    wsRef.current = ws
    ws.onmessage = (ev) => {
      try {
        pushEvent(JSON.parse(ev.data) as TelemetryEvent)
      } catch {
        /* ignore malformed frame */
      }
    }
    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [sessionId, pushEvent, clearEvents])
}
