import type { User } from '@/features/auth/types/auth.types'
export type ProjectCreationPolicy = 'restricted' | 'open'

export interface Workspace {
  id: string
  name: string
  project_creation_policy: ProjectCreationPolicy
  created_at: string
}

export interface WorkspaceMember {
  id: string
  workspace_id: string
  user_id: string
  is_owner: boolean
  joined_at: string
  user?: User
}

export interface WorkspaceCreate {
  name: string
}

export interface WorkspaceUpdate {
  name?: string
  project_creation_policy?: ProjectCreationPolicy
}