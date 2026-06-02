import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { inboxApi } from '../api/inboxApi'
import type { SendInvite } from '../types/inbox.types'
import { toast } from '@/shared/hooks/useToast'

export const useInbox = () =>
  useQuery({ queryKey: ['inbox'], queryFn: inboxApi.list })

export const useUnreadCount = () => {
  const { data } = useInbox()
  if (!data) return 0
  return data.filter((i) => i.type === 'invite' && i.status === 'pending').length
    + data.filter((i) => i.type === 'notification' && i.status === 'unread').length
}

export const useAcceptInvite = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => inboxApi.acceptInvite(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inbox'] })
      qc.invalidateQueries({ queryKey: ['workspaces'] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast('Invite accepted', 'success')
    },
    onError: () => toast('Failed to accept invite', 'error'),
  })
}

export const useDeclineInvite = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => inboxApi.declineInvite(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inbox'] }) },
    onError: () => toast('Failed to decline invite', 'error'),
  })
}

export const useMarkRead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => inboxApi.markRead(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inbox'] }) },
  })
}

export const useSendWorkspaceInvite = (workspaceId: string) => {
  return useMutation({
    mutationFn: (data: SendInvite) => inboxApi.sendWorkspaceInvite(workspaceId, data),
    onSuccess: () => toast('Invite sent', 'success'),
    onError: () => toast('Failed to send invite', 'error'),
  })
}

export const useSendProjectInvite = (projectId: string) => {
  return useMutation({
    mutationFn: (data: SendInvite) => inboxApi.sendProjectInvite(projectId, data),
    onSuccess: () => toast('Invite sent', 'success'),
    onError: () => toast('Failed to send invite', 'error'),
  })
}

export const useSendChannelInvite = (channelId: string) => {
  return useMutation({
    mutationFn: (data: SendInvite) => inboxApi.sendChannelInvite(channelId, data),
    onSuccess: () => toast('Invite sent', 'success'),
    onError: () => toast('Failed to send invite', 'error'),
  })
}