export type AgentRunStatus =
  | 'pending'
  | 'running'
  | 'awaiting_review'
  | 'approved'
  | 'rejected'
  | 'failed'

export type PlanActionType = 'create' | 'modify' | 'delete' | 'no_op'

export interface PlanStep {
  step_number: number
  description: string
  action_type: PlanActionType
  target_file_path: string
  explanation: string
}

export interface DevelopmentPlan {
  summary: string
  steps: PlanStep[]
  affected_files: string[]
}

export interface AgentRunRead {
  id: string
  ticket_id: string
  status: AgentRunStatus
  plan_json: DevelopmentPlan | null
  attempt_count: number
  edited_by_user_id: string | null
  edited_at: string | null
  created_at: string
  updated_at: string
}