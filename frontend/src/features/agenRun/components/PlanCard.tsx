import { useState } from 'react'
import { Btn } from '@/shared/components'
import { useAgentRun, useApprovePlan, useRejectPlan } from '../hooks/useAgenRun'
import type { AgentRunStatus, PlanActionType } from '../types/agentRun.types'
import { PlanEditModal } from './PlanEditModal'
import styles from './PlanCard.module.css'

const STATUS_LABEL: Record<AgentRunStatus, string> = {
  pending: 'Preparing…',
  running: 'Generating…',
  awaiting_review: 'Awaiting review',
  approved: 'Approved',
  rejected: 'Rejected',
  failed: 'Failed',
}

const STATUS_PILL_CLASS: Record<AgentRunStatus, string> = {
  pending: styles.statusNeutral,
  running: styles.statusNeutral,
  awaiting_review: styles.statusAwaiting,
  approved: styles.statusApproved,
  rejected: styles.statusRejected,
  failed: styles.statusRejected,
}

const ACTION_BADGE_CLASS: Record<PlanActionType, string> = {
  create: styles.actionCreate,
  modify: styles.actionModify,
  delete: styles.actionDelete,
  no_op: styles.actionNoOp,
}

const STEPS_PREVIEW_COUNT = 4

interface PlanCardProps {
  runId: string
  ticketId: string
  canReview: boolean
}

export function PlanCard({ runId, ticketId, canReview }: PlanCardProps) {
  const { data: run, isLoading, isError } = useAgentRun(runId)
  const approve = useApprovePlan(runId, ticketId)
  const reject = useRejectPlan(runId, ticketId)
  const [expanded, setExpanded] = useState(false)
  const [showEdit, setShowEdit] = useState(false)

  if (isLoading) {
    return (
      <div className={styles.card}>
        <div className={styles.header}>
          <span className={styles.icon}>⬡</span>
          <span className={styles.title}>Loading development plan…</span>
        </div>
      </div>
    )
  }

  if (isError || !run) {
    return (
      <div className={styles.card}>
        <div className={styles.header}>
          <span className={styles.icon}>⬡</span>
          <span className={styles.title}>Development plan</span>
        </div>
        <p className={styles.errorNote}>Couldn't load the full plan — try refreshing.</p>
      </div>
    )
  }

  const plan = run.plan_json
  const steps = plan?.steps ?? []
  const visibleSteps = expanded ? steps : steps.slice(0, STEPS_PREVIEW_COUNT)
  const hasMore = steps.length > STEPS_PREVIEW_COUNT

  const isPending = run.status === 'awaiting_review'
  const isBusy = approve.isPending || reject.isPending

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.icon}>⬡</span>
        <span className={styles.title}>AI Development Plan</span>
        <span className={`${styles.statusPill} ${STATUS_PILL_CLASS[run.status]}`}>
          {STATUS_LABEL[run.status]}
        </span>
      </div>

      {plan ? (
        <>
          <p className={styles.summary}>{plan.summary}</p>

          <div className={styles.stepsList}>
            {visibleSteps.map((step) => (
              <div key={step.step_number} className={styles.step}>
                <span className={styles.stepNumber}>{step.step_number}</span>
                <div className={styles.stepBody}>
                  <div className={styles.stepMeta}>
                    <span className={`${styles.actionBadge} ${ACTION_BADGE_CLASS[step.action_type]}`}>
                      {step.action_type.replace('_', '-')}
                    </span>
                    {step.target_file_path && step.target_file_path.toUpperCase() !== 'N/A' && (
                      <span className={styles.filePath}>{step.target_file_path}</span>
                    )}
                  </div>
                  <p className={styles.stepDescription}>{step.description}</p>
                  <p className={styles.stepExplanation}>{step.explanation}</p>
                </div>
              </div>
            ))}
          </div>

          {steps.length > STEPS_PREVIEW_COUNT && (
            <button className={styles.expandBtn} onClick={() => setExpanded((v) => !v)}>
              {expanded ? 'Show fewer' : `Show all ${steps.length} steps`}
            </button>
          )}

          {plan.affected_files.length > 0 && (
            <p className={styles.filesLabel}>
              {plan.affected_files.length} file{plan.affected_files.length !== 1 ? 's' : ''} affected
            </p>
          )}
        </>
      ) : (
        <p className={styles.errorNote}>Plan content isn't available yet.</p>
      )}

      {run.edited_at && (
        <p className={styles.editedNote}>Edited by a Team Lead since generation.</p>
      )}

      {canReview && isPending && (
        <div className={styles.actions}>
          <Btn size="sm" variant="primary" onClick={() => approve.mutate()} loading={approve.isPending} disabled={isBusy}>
            Approve
          </Btn>
          <Btn size="sm" variant="ghost" onClick={() => setShowEdit(true)} disabled={isBusy}>
            Edit
          </Btn>
          <Btn size="sm" variant="ghost" onClick={() => reject.mutate()} loading={reject.isPending} disabled={isBusy}>
            Reject
          </Btn>
        </div>
      )}

      {showEdit && plan && (
        <PlanEditModal
          runId={runId}
          ticketId={ticketId}
          plan={plan}
          onClose={() => setShowEdit(false)}
        />
      )}
    </div>
  )
}