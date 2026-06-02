import type { User } from '@/features/auth/types/auth.types'
export type ChannelDiscipline = 'frontend' | 'backend' | 'database' | 'devops' | 'ai_ml'
export type ApprovalPolicy = 'lead_only' | 'any_member'
export type ChannelMemberRole = 'channel_lead' | 'member'

export interface Channel {
  id: string
  project_id: string
  name: string
  discipline: ChannelDiscipline | null
  is_leads_channel: boolean
  approval_policy: ApprovalPolicy
  created_at: string
}

export interface ChannelMember {
  id: string
  channel_id: string
  user_id: string
  user?: User

  role: ChannelMemberRole
  joined_at: string
}

export interface ChannelCreate {
  name: string
  discipline: ChannelDiscipline
  approval_policy?: ApprovalPolicy
}

export interface ChannelUpdate {
  name?: string
  approval_policy?: ApprovalPolicy
}

export interface ChannelMemberAdd {
  user_id: string
  role?: ChannelMemberRole
}

export interface ChannelMemberUpdate {
  role: ChannelMemberRole
}