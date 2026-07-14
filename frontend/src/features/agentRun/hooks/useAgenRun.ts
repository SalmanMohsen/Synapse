import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentRunApi } from '../api/agenRunApi'
import type { DevelopmentPlan } from '../types/agentRun.types'
import { toast } from '@/shared/hooks/useToast'

export const useAgentRun = (runId: string | null) =>
  useQuery({
    queryKey: ['agent-run', runId],
    queryFn: () => agentRunApi.get(runId!),
    enabled: !!runId,
  })

export const useApprovePlan = (runId: string, ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => agentRunApi.approve(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-run', runId] })
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['messages', ticketId] })
      toast('Plan approved — handed off to the Code Agent', 'success')
    },
    onError: () => toast('Failed to approve the plan', 'error'),
  })
}

export const useRejectPlan = (runId: string, ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => agentRunApi.reject(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-run', runId] })
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['messages', ticketId] })
      toast('Plan rejected', 'info')
    },
    onError: () => toast('Failed to reject the plan', 'error'),
  })
}

export const useEditPlan = (runId: string, ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (plan: DevelopmentPlan) => agentRunApi.edit(runId, plan),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-run', runId] })
      qc.invalidateQueries({ queryKey: ['messages', ticketId] })
      toast('Plan updated', 'success')
    },
    // No generic onError toast — PlanEditModal surfaces the exact grounding
    // validation message (400 detail) inline so the user knows which step to fix.
  })
}