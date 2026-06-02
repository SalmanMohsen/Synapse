import { api } from '@/shared/lib/axios'
import type { Workspace, WorkspaceMember, WorkspaceCreate, WorkspaceUpdate } from '../types/workspace.types'

export const workspaceApi = {
  list: (): Promise<Workspace[]> =>
    api.get<Workspace[]>('/workspaces').then((r) => r.data),

  get: (id: string): Promise<Workspace> =>
    api.get<Workspace>(`/workspaces/${id}`).then((r) => r.data),

  create: (data: WorkspaceCreate): Promise<Workspace> =>
    api.post<Workspace>('/workspaces', data).then((r) => r.data),

  update: (id: string, data: WorkspaceUpdate): Promise<Workspace> =>
    api.patch<Workspace>(`/workspaces/${id}`, data).then((r) => r.data),

  delete: (id: string): Promise<void> =>
    api.delete(`/workspaces/${id}`).then(() => undefined),

  listMembers: (id: string): Promise<WorkspaceMember[]> =>
    api.get<WorkspaceMember[]>(`/workspaces/${id}/members`).then((r) => r.data),

  promoteToOwner: (workspaceId: string, userId: string): Promise<WorkspaceMember> =>
    api.post<WorkspaceMember>(`/workspaces/${workspaceId}/members/${userId}/promote`).then((r) => r.data),

  removeMember: (workspaceId: string, userId: string): Promise<void> =>
    api.delete(`/workspaces/${workspaceId}/members/${userId}`).then(() => undefined),
}