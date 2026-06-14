import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ticketApi } from '../api/ticketApi'
import type { TicketCreate, TicketUpdate, TicketRouteRequest, TicketRead } from '../types/ticket.types'
import { toast } from '@/shared/hooks/useToast'

export const useTickets = (channelId: string) =>
  useQuery({
    queryKey: ['tickets', channelId],
    queryFn: () => ticketApi.list(channelId),
    enabled: !!channelId,
  })

export const useTicketDetail = (ticketId: string) =>
  useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => ticketApi.get(ticketId),
    enabled: !!ticketId,
  })

export const useCreateTicket = (channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TicketCreate) => ticketApi.create(channelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickets', channelId] })
      toast('Ticket created', 'success')
    },
    onError: () => toast('Failed to create ticket', 'error'),
  })
}

export const useUpdateTicket = (ticketId: string, channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TicketUpdate) => ticketApi.update(ticketId, data),
    onSuccess: (ticket) => {
      qc.setQueryData(['ticket', ticketId], (old: unknown) =>
        old ? { ...(old as object), ticket } : old
      )
      qc.invalidateQueries({ queryKey: ['tickets', channelId] })
    },
    onError: () => toast('Failed to update ticket', 'error'),
  })
}

export const useActivateTicket = (ticketId: string, channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => ticketApi.activate(ticketId),
    onSuccess: (ticket) => {
      _patchTicketCache(qc, ticketId, channelId, ticket)
      toast('Ticket activated', 'success')
    },
    onError: () => toast('Failed to activate ticket', 'error'),
  })
}

export const useDeactivateTicket = (ticketId: string, channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => ticketApi.deactivate(ticketId),
    onSuccess: (ticket) => {
      _patchTicketCache(qc, ticketId, channelId, ticket)
      toast('Ticket moved to backlog', 'success')
    },
    onError: () => toast('Failed to deactivate ticket', 'error'),
  })
}

export const useRouteTicket = (ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TicketRouteRequest) => ticketApi.route(ticketId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      toast('Ticket routed', 'success')
    },
    onError: () => toast('Failed to route ticket', 'error'),
  })
}

// ── Internal helper ───────────────────────────────────────────────────────────

function _patchTicketCache(
  qc: ReturnType<typeof useQueryClient>,
  ticketId: string,
  channelId: string,
  ticket: TicketRead,
) {
  qc.setQueryData(['ticket', ticketId], (old: unknown) =>
    old ? { ...(old as object), ticket } : old
  )
  qc.setQueryData(['tickets', channelId], (old: TicketRead[] | undefined) =>
    old ? old.map((t) => (t.id === ticketId ? ticket : t)) : old
  )
}