import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { channelApi } from '../api/channelApi'
import type { ChannelCreate, ChannelUpdate, ChannelMemberAdd, ChannelMemberUpdate } from '../types/channel.types'
import { toast } from '@/shared/hooks/useToast'

export const useChannels = (projectId: string) =>
  useQuery({ queryKey: ['channels', projectId], queryFn: () => channelApi.list(projectId), enabled: !!projectId })

export const useChannel = (id: string) =>
  useQuery({ queryKey: ['channel', id], queryFn: () => channelApi.get(id), enabled: !!id })

export const useChannelMembers = (id: string) =>
  useQuery({ queryKey: ['channel-members', id], queryFn: () => channelApi.listMembers(id), enabled: !!id })

export const useCreateChannel = (projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ChannelCreate) => channelApi.create(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['channels', projectId] }) },
    onError: () => toast('Failed to create channel', 'error'),
  })
}

export const useUpdateChannel = (id: string, projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ChannelUpdate) => channelApi.update(id, data),
    onSuccess: (ch) => {
      qc.setQueryData(['channel', id], ch)
      qc.invalidateQueries({ queryKey: ['channels', projectId] })
      toast('Channel updated', 'success')
    },
    onError: () => toast('Failed to update channel', 'error'),
  })
}

export const useDeleteChannel = (projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => channelApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['channels', projectId] }) },
    onError: () => toast('Failed to delete channel', 'error'),
  })
}

export const useAddChannelMember = (channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ChannelMemberAdd) => channelApi.addMember(channelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['channel-members', channelId] })
      toast('Member added', 'success')
    },
    onError: () => toast('Failed to add member', 'error'),
  })
}

export const useUpdateChannelMember = (channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: ChannelMemberUpdate }) =>
      channelApi.updateMember(channelId, userId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['channel-members', channelId] }) },
    onError: () => toast('Failed to update role', 'error'),
  })
}

export const useRemoveChannelMember = (channelId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => channelApi.removeMember(channelId, userId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['channel-members', channelId] }) },
    onError: () => toast('Failed to remove member', 'error'),
  })
}