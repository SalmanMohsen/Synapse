import type { User } from '@/features/auth/types/auth.types'
export type ProjectRole = 'team_lead' | 'member' | 'advisor' | 'viewer'

export interface Project {
  id: string
  workspace_id: string
  name: string
  github_app_installation_id: string | null
  default_branch: string
  created_at: string
}

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  role: ProjectRole
  joined_at: string
  user?: User
}

export interface ProjectCreate {
  name: string
  default_branch?: string
}

export interface ProjectUpdate {
  name?: string
  default_branch?: string
}

export interface ProjectMemberAdd {
  user_id: string
  role?: ProjectRole
}

export interface ProjectMemberUpdate {
  role: ProjectRole
}