import { api } from '@/shared/lib/axios'
import type { MessageCreate, MessageListResponse, MessageRead, MessageUpdate } from '../types/message.types'

export const messageApi = {
  list: (ticketId: string, beforeId?: string): Promise<MessageListResponse> =>
    api.get<MessageListResponse>(`/tickets/${ticketId}/messages`, {
      params: beforeId ? { before_id: beforeId } : undefined,
    }).then((r) => r.data),

  create: (ticketId: string, data: MessageCreate): Promise<MessageRead> =>
    api.post<MessageRead>(`/tickets/${ticketId}/messages`, data).then((r) => r.data),

  edit: (ticketId: string, messageId: string, data: MessageUpdate): Promise<MessageRead> =>
    api.patch<MessageRead>(`/tickets/${ticketId}/messages/${messageId}`, data).then((r) => r.data),

  delete: (ticketId: string, messageId: string): Promise<MessageRead> =>
    api.delete<MessageRead>(`/tickets/${ticketId}/messages/${messageId}`).then((r) => r.data),
}