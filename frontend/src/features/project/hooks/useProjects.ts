import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { projectApi } from '../api/projectApi'
import type { ProjectCreate, ProjectUpdate, ProjectMemberAdd, ProjectMemberUpdate } from '../types/project.types'
import { toast } from '@/shared/hooks/useToast'

export const useProjects = (workspaceId: string) =>
  useQuery({ queryKey: ['projects', workspaceId], queryFn: () => projectApi.list(workspaceId), enabled: !!workspaceId })

export const useProject = (id: string) =>
  useQuery({ queryKey: ['project', id], queryFn: () => projectApi.get(id), enabled: !!id })

export const useProjectMembers = (id: string) =>
  useQuery({ queryKey: ['project-members', id], queryFn: () => projectApi.listMembers(id), enabled: !!id })

export const useCreateProject = (workspaceId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProjectCreate) => projectApi.create(workspaceId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects', workspaceId] }) },
    onError: () => toast('Failed to create project', 'error'),
  })
}

export const useUpdateProject = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProjectUpdate) => projectApi.update(id, data),
    onSuccess: (p) => {
      qc.setQueryData(['project', id], p)
      qc.invalidateQueries({ queryKey: ['projects', p.workspace_id] })
      toast('Project updated', 'success')
    },
    onError: () => toast('Failed to update project', 'error'),
  })
}

export const useDeleteProject = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, workspaceId }: { id: string; workspaceId: string }) =>
      projectApi.delete(id).then(() => ({ workspaceId })),
    onSuccess: (_, vars) => { qc.invalidateQueries({ queryKey: ['projects', vars.workspaceId] }) },
    onError: () => toast('Failed to delete project', 'error'),
  })
}

export const useAddProjectMember = (projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProjectMemberAdd) => projectApi.addMember(projectId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project-members', projectId] })
      toast('Member added', 'success')
    },
    onError: () => toast('Failed to add member', 'error'),
  })
}

export const useUpdateProjectMember = (projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: ProjectMemberUpdate }) =>
      projectApi.updateMember(projectId, userId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', projectId] }) },
    onError: () => toast('Failed to update role', 'error'),
  })
}

export const useRemoveProjectMember = (projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => projectApi.removeMember(projectId, userId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', projectId] }) },
    onError: () => toast('Failed to remove member', 'error'),
  })
}