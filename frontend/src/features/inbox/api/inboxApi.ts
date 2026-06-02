import { api } from '@/shared/lib/axios'
import type { InboxItem, SendInvite } from '../types/inbox.types'

export const inboxApi = {
  list: (): Promise<InboxItem[]> =>
    api.get<InboxItem[]>('/inbox').then((r) => r.data),

  acceptInvite: (id: string): Promise<InboxItem> =>
    api.post<InboxItem>(`/inbox/invites/${id}/accept`).then((r) => r.data),

  declineInvite: (id: string): Promise<InboxItem> =>
    api.post<InboxItem>(`/inbox/invites/${id}/decline`).then((r) => r.data),

  markRead: (id: string): Promise<InboxItem> =>
    api.patch<InboxItem>(`/inbox/${id}/read`).then((r) => r.data),

  sendWorkspaceInvite: (workspaceId: string, data: SendInvite): Promise<InboxItem> =>
    api.post<InboxItem>(`/workspaces/${workspaceId}/invites`, data).then((r) => r.data),

  sendProjectInvite: (projectId: string, data: SendInvite): Promise<InboxItem> =>
    api.post<InboxItem>(`/projects/${projectId}/invites`, data).then((r) => r.data),

  sendChannelInvite: (channelId: string, data: SendInvite): Promise<InboxItem> =>
    api.post<InboxItem>(`/channels/${channelId}/invites`, data).then((r) => r.data),
}