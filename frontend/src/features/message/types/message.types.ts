export type MessageType =
  | 'human'
  | 'agent_approval_card'
  | 'agent_plan_card'
  | 'agent_progress'
  | 'agent_blocker'
  | 'system'

export interface MessageAuthor {
  id: string
  display_name: string
  avatar_url: string | null
}

export interface MessageRead {
  id: string
  ticket_id: string
  author_id: string | null
  author: MessageAuthor | null
  /** null when soft-deleted */
  content: string | null
  type: MessageType
  metadata_json: Record<string, unknown> | null
  deleted_at: string | null
  edited_at: string | null
  created_at: string
  updated_at: string
}

export interface MessageCreate {
  content: string
}

export interface MessageUpdate {
  content: string
}

export interface MessageListResponse {
  items: MessageRead[]
  has_more: boolean
  /** pass as `before_id` to fetch the next (older) page */
  next_cursor: string | null
}