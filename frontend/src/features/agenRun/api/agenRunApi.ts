import { api } from '@/shared/lib/axios'
import type { AgentRunRead, DevelopmentPlan } from '../types/agentRun.types'

export const agentRunApi = {
  get: (runId: string): Promise<AgentRunRead> =>
    api.get<AgentRunRead>(`/agent-runs/${runId}`).then((r) => r.data),

  approve: (runId: string): Promise<void> =>
    api.post(`/agent-runs/${runId}/approve`).then(() => undefined),

  reject: (runId: string): Promise<void> =>
    api.post(`/agent-runs/${runId}/reject`).then(() => undefined),

  edit: (runId: string, plan: DevelopmentPlan): Promise<DevelopmentPlan> =>
    api.patch<DevelopmentPlan>(`/agent-runs/${runId}`, { plan_json: plan }).then((r) => r.data),
}