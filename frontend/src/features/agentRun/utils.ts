import type { MessageRead } from '@/features/message/types/message.types'

/**
 * Identifies a Planning Agent "plan ready" message and extracts the AgentRun id.
 *
 * Backend currently posts this as type="system" with
 * metadata_json.event === "plan_generated" (see planning-service/app/worker.py).
 * The `agent_plan_card` branch is kept so this keeps working with no changes
 * if the backend later switches to that dedicated MessageType.
 */
export function getPlanCardRunId(message: MessageRead): string | null {
  const meta = message.metadata_json
  const isPlanReady =
    message.type === 'agent_plan_card' ||
    (message.type === 'system' && meta?.event === 'plan_generated')

  if (!isPlanReady) return null
  const runId = meta?.agent_run_id
  return typeof runId === 'string' ? runId : null
}