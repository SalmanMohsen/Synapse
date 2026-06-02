import { api } from '@/shared/lib/axios'
import type { Project, ProjectMember, ProjectCreate, ProjectUpdate, ProjectMemberAdd, ProjectMemberUpdate } from '../types/project.types'

export const projectApi = {
  list: (workspaceId: string): Promise<Project[]> =>
    api.get<Project[]>(`/workspaces/${workspaceId}/projects`).then((r) => r.data),

  get: (id: string): Promise<Project> =>
    api.get<Project>(`/projects/${id}`).then((r) => r.data),

  create: (workspaceId: string, data: ProjectCreate): Promise<Project> =>
    api.post<Project>(`/workspaces/${workspaceId}/projects`, data).then((r) => r.data),

  update: (id: string, data: ProjectUpdate): Promise<Project> =>
    api.patch<Project>(`/projects/${id}`, data).then((r) => r.data),

  delete: (id: string): Promise<void> =>
    api.delete(`/projects/${id}`).then(() => undefined),

  listMembers: (id: string): Promise<ProjectMember[]> =>
    api.get<ProjectMember[]>(`/projects/${id}/members`).then((r) => r.data),

  addMember: (id: string, data: ProjectMemberAdd): Promise<ProjectMember> =>
    api.post<ProjectMember>(`/projects/${id}/members`, data).then((r) => r.data),

  updateMember: (projectId: string, userId: string, data: ProjectMemberUpdate): Promise<ProjectMember> =>
    api.patch<ProjectMember>(`/projects/${projectId}/members/${userId}`, data).then((r) => r.data),

  removeMember: (projectId: string, userId: string): Promise<void> =>
    api.delete(`/projects/${projectId}/members/${userId}`).then(() => undefined),
}