import { api } from '@/shared/lib/axios'
import type {
  TicketCreate,
  TicketUpdate,
  TicketRead,
  TicketRouteRequest,
  TicketSplitRequest,
} from '../types/ticket.types'
import type { TicketDetailResponse } from '../types/ticket.types'

// Re-export the composite response type here so hooks can import it cleanly
export type { TicketDetailResponse }

export const ticketApi = {
  list: (channelId: string): Promise<TicketRead[]> =>
    api.get<TicketRead[]>(`/channels/${channelId}/tickets`).then((r) => r.data),

  get: (ticketId: string): Promise<TicketDetailResponse> =>
    api.get<TicketDetailResponse>(`/tickets/${ticketId}`).then((r) => r.data),

  create: (channelId: string, data: TicketCreate): Promise<TicketRead> =>
    api.post<TicketRead>(`/channels/${channelId}/tickets`, data).then((r) => r.data),

  update: (ticketId: string, data: TicketUpdate): Promise<TicketRead> =>
    api.patch<TicketRead>(`/tickets/${ticketId}`, data).then((r) => r.data),

  activate: (ticketId: string): Promise<TicketRead> =>
    api.post<TicketRead>(`/tickets/${ticketId}/activate`).then((r) => r.data),

  deactivate: (ticketId: string): Promise<TicketRead> =>
    api.post<TicketRead>(`/tickets/${ticketId}/deactivate`).then((r) => r.data),

  route: (ticketId: string, data: TicketRouteRequest): Promise<TicketRead> =>
    api.post<TicketRead>(`/tickets/${ticketId}/route`, data).then((r) => r.data),

  split: (ticketId: string, data: TicketSplitRequest): Promise<TicketRead> =>
    api.post<TicketRead>(`/tickets/${ticketId}/split`, data).then((r) => r.data),
}