export type InboxItemType = 'invite' | 'notification'
export type InboxItemStatus = 'pending' | 'accepted' | 'declined' | 'read' | 'unread'

export interface InboxItem {
  id: string
  user_id: string
  type: InboxItemType
  status: InboxItemStatus
  sender_id: string | null
  workspace_id: string | null
  project_id: string | null
  channel_id: string | null
  role: string | null
  title: string
  body: string | null
  entity_type: string | null
  entity_id: string | null
  expires_at: string | null
  created_at: string
}

export interface SendInvite {
  target_user_id: string
  role?: string
}