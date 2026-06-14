import type { MessageListResponse } from '@/features/message/types/message.types'

// 1. Add 'routed' to the TicketStatus union
export type TicketStatus =
  | 'backlog'
  | 'routed'
  | 'active'
  | 'in_discussion'
  | 'consensus_reached'
  | 'plan_review'
  | 'agent_working'
  | 'in_review'
  | 'merged'
  | 'closed'

export type TicketPriority = 'low' | 'medium' | 'high' | 'critical'
export type TicketSource = 'manual' | 'github_issue'

export interface TicketRead {
  id: string
  channel_id: string
  title: string
  description: string | null
  status: TicketStatus
  source: TicketSource
  priority: TicketPriority
  creator_id: string | null
  github_issue_number: number | null
  github_author_login: string | null
  github_pr_number: number | null
  parent_ticket_id: string | null
  created_at: string
  updated_at: string
}

export interface ThreadStateRead {
  id: string
  ticket_id: string
  rolling_summary: string | null
  structured_state_json: Record<string, unknown> | null
  last_processed_message_id: string | null
  created_at: string
  updated_at: string
}

export interface TicketDetailResponse {
  ticket: TicketRead
  messages: MessageListResponse
  thread_state: ThreadStateRead | null
}

export interface TicketCreate {
  title: string
  description?: string
  priority?: TicketPriority
}

export interface TicketUpdate {
  title?: string
  description?: string
  priority?: TicketPriority
}

export interface TicketRouteRequest {
  channel_id: string
}

export interface TicketSplitRequest {
  child_ticket_ids: string[]
}

// ── Display helpers ───────────────────────────────────────────────────────────

// 2. Add the 'routed' key and its label mapping
export const STATUS_LABELS: Record<TicketStatus, string> = {
  backlog:           'Backlog',
  routed:            'Routed',
  active:            'Active',
  in_discussion:     'In discussion',
  consensus_reached: 'Consensus',
  plan_review:       'Plan review',
  agent_working:     'Agent working',
  in_review:         'In review',
  merged:            'Merged',
  closed:            'Closed',
}

export const PRIORITY_LABELS: Record<TicketPriority, string> = {
  low:      'Low',
  medium:   'Medium',
  high:     'High',
  critical: 'Critical',
}