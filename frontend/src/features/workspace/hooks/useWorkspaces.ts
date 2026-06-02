import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workspaceApi } from '../api/workspaceApi'
import type { WorkspaceCreate, WorkspaceUpdate } from '../types/workspace.types'
import { toast } from '@/shared/hooks/useToast'

export const useWorkspaces = () =>
  useQuery({ queryKey: ['workspaces'], queryFn: workspaceApi.list })

export const useWorkspace = (id: string) =>
  useQuery({ queryKey: ['workspace', id], queryFn: () => workspaceApi.get(id), enabled: !!id })

export const useWorkspaceMembers = (id: string) =>
  useQuery({ queryKey: ['workspace-members', id], queryFn: () => workspaceApi.listMembers(id), enabled: !!id })

export const useCreateWorkspace = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: WorkspaceCreate) => workspaceApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workspaces'] }) },
    onError: () => toast('Failed to create workspace', 'error'),
  })
}

export const useUpdateWorkspace = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: WorkspaceUpdate) => workspaceApi.update(id, data),
    onSuccess: (ws) => {
      qc.setQueryData(['workspace', id], ws)
      qc.invalidateQueries({ queryKey: ['workspaces'] })
      toast('Workspace updated', 'success')
    },
    onError: () => toast('Failed to update workspace', 'error'),
  })
}

export const useDeleteWorkspace = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => workspaceApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workspaces'] }) },
    onError: () => toast('Failed to delete workspace', 'error'),
  })
}

export const usePromoteToOwner = (workspaceId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => workspaceApi.promoteToOwner(workspaceId, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workspace-members', workspaceId] })
      toast('Member promoted to owner', 'success')
    },
    onError: () => toast('Failed to promote member', 'error'),
  })
}

export const useRemoveWorkspaceMember = (workspaceId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => workspaceApi.removeMember(workspaceId, userId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workspace-members', workspaceId] }) },
    onError: () => toast('Failed to remove member', 'error'),
  })
}