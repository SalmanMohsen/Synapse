import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/features/auth/store/authSlice'

export function useWebSocket() {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!user) {
      if (wsRef.current) {
        wsRef.current.close()
      }
      return
    }

    function connect() {
      const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const wsUrl = baseUrl.replace(/^http/, 'ws') + '/ws'

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          handleServerEvent(payload)
        } catch (err) {
          // Silent catch for malformed frames
        }
      }

      ws.onclose = (e) => {
        // Only attempt reconnect if not intentionally closed (code 4001 or no user)
        if (e.code !== 4001 && user) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, 3000)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [user, queryClient])

  function handleServerEvent(data: any) {
    // Aligns with the backend dictionary's 'event' field
    const eventType = data.event

    if (eventType === 'message.new' || eventType === 'message.updated') {
      const { ticket_id, channel_id } = data
      if (ticket_id) {
        // Invalidate infinite message scroll cache & composite ticket detail (for rolling summary)
        queryClient.invalidateQueries({ queryKey: ['messages', ticket_id] })
        queryClient.invalidateQueries({ queryKey: ['ticket', ticket_id] })
      }
      if (channel_id) {
        queryClient.invalidateQueries({ queryKey: ['tickets', channel_id] })
      }

    } else if (eventType === 'ticket.status_change') {
      const { ticket_id, channel_id } = data
      if (ticket_id) {
        queryClient.invalidateQueries({ queryKey: ['ticket', ticket_id] })
        // Invalidate message thread so the automated system message displays in real-time
        queryClient.invalidateQueries({ queryKey: ['messages', ticket_id] })
        queryClient.invalidateQueries({ queryKey: ['agent-run'] })
      }
      if (channel_id) {
        queryClient.invalidateQueries({ queryKey: ['tickets', channel_id] })
      }
    // ADD THIS BRANCH:
    } else if (eventType === 'ticket.new') {
      const { channel_id } = data
      if (channel_id) {
        queryClient.invalidateQueries({ queryKey: ['tickets', channel_id] })
      }
    }
     else if (eventType === 'ticket.routed') {
      const { ticket_id, from_channel_id, to_channel_id } = data
      if (ticket_id) {
        queryClient.invalidateQueries({ queryKey: ['ticket', ticket_id] })
        // Invalidate message thread so the "routed to" system message displays in real-time
        queryClient.invalidateQueries({ queryKey: ['messages', ticket_id] })
      }
      if (from_channel_id) {
        queryClient.invalidateQueries({ queryKey: ['tickets', from_channel_id] })
      }
      if (to_channel_id) {
        queryClient.invalidateQueries({ queryKey: ['tickets', to_channel_id] })
      }
    } else if (eventType === 'notification.new') {
      queryClient.invalidateQueries({ queryKey: ['inbox'] })
    }
  }
}