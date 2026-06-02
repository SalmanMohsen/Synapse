import { api } from '@/shared/lib/axios'
import type { Channel, ChannelMember, ChannelCreate, ChannelUpdate, ChannelMemberAdd, ChannelMemberUpdate } from '../types/channel.types'

export const channelApi = {
  list: (projectId: string): Promise<Channel[]> =>
    api.get<Channel[]>(`/projects/${projectId}/channels`).then((r) => r.data),

  get: (id: string): Promise<Channel> =>
    api.get<Channel>(`/channels/${id}`).then((r) => r.data),

  create: (projectId: string, data: ChannelCreate): Promise<Channel> =>
    api.post<Channel>(`/projects/${projectId}/channels`, data).then((r) => r.data),

  createLeadsChannel: (projectId: string): Promise<Channel> =>
    api.post<Channel>(`/projects/${projectId}/leads-channel`).then((r) => r.data),

  update: (id: string, data: ChannelUpdate): Promise<Channel> =>
    api.patch<Channel>(`/channels/${id}`, data).then((r) => r.data),

  delete: (id: string): Promise<void> =>
    api.delete(`/channels/${id}`).then(() => undefined),

  listMembers: (id: string): Promise<ChannelMember[]> =>
    api.get<ChannelMember[]>(`/channels/${id}/members`).then((r) => r.data),

  addMember: (id: string, data: ChannelMemberAdd): Promise<ChannelMember> =>
    api.post<ChannelMember>(`/channels/${id}/members`, data).then((r) => r.data),

  updateMember: (channelId: string, userId: string, data: ChannelMemberUpdate): Promise<ChannelMember> =>
    api.patch<ChannelMember>(`/channels/${channelId}/members/${userId}`, data).then((r) => r.data),

  removeMember: (channelId: string, userId: string): Promise<void> =>
    api.delete(`/channels/${channelId}/members/${userId}`).then(() => undefined),
}