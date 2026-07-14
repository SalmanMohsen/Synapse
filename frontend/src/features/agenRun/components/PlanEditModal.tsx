import { useState } from 'react'
import { Modal, Btn, SelectField, TextField } from '@/shared/components'
import { useEditPlan } from '../hooks/useAgenRun'
import type { DevelopmentPlan, PlanStep, PlanActionType } from '../types/agentRun.types'
import styles from './PlanCard.module.css'

const ACTION_OPTIONS: { value: PlanActionType; label: string }[] = [
  { value: 'create', label: 'Create' },
  { value: 'modify', label: 'Modify' },
  { value: 'delete', label: 'Delete' },
  { value: 'no_op', label: 'No-op' },
]

interface PlanEditModalProps {
  runId: string
  ticketId: string
  plan: DevelopmentPlan
  onClose: () => void
}

export function PlanEditModal({ runId, ticketId, plan, onClose }: PlanEditModalProps) {
  const editPlan = useEditPlan(runId, ticketId)
  const [summary, setSummary] = useState(plan.summary)
  const [steps, setSteps] = useState<PlanStep[]>(plan.steps)
  const [formError, setFormError] = useState<string | null>(null)

  const updateStep = (index: number, patch: Partial<PlanStep>) => {
    setSteps((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }

  const removeStep = (index: number) => {
    if (steps.length <= 1) return // keep at least one step
    setSteps((prev) => prev.filter((_, i) => i !== index))
  }

  const addStep = () => {
    setSteps((prev) => [
      ...prev,
      { step_number: prev.length + 1, description: '', action_type: 'modify', target_file_path: '', explanation: '' },
    ])
  }

  const handleSave = async () => {
    setFormError(null)
    const renumbered = steps.map((s, i) => ({ ...s, step_number: i + 1 }))

    for (const s of renumbered) {
      if (s.action_type !== 'no_op' && !s.target_file_path.trim()) {
        setFormError(`Step ${s.step_number}: a target file path is required for '${s.action_type}' actions.`)
        return
      }
      if (!s.description.trim() || !s.explanation.trim()) {
        setFormError(`Step ${s.step_number}: description and explanation can't be empty.`)
        return
      }
    }

    const affected_files = Array.from(
      new Set(
        renumbered
          .filter((s) => s.action_type !== 'no_op' && s.target_file_path.trim())
          .map((s) => s.target_file_path.trim())
      )
    )

    try {
      await editPlan.mutateAsync({ summary, steps: renumbered, affected_files })
      onClose()
    } catch (err: any) {
      setFormError(err?.response?.data?.detail ?? 'Failed to save changes — please try again.')
    }
  }

  return (
    <Modal
      title="Edit development plan"
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleSave} loading={editPlan.isPending}>
            Save changes
          </Btn>
        </>
      }
    >
      {formError && <p className={styles.formError}>{formError}</p>}

      <label className={styles.fieldLabel}>Summary</label>
      <textarea
        className={styles.editTextarea}
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
        rows={2}
      />

      <div className={styles.editStepsHeader}>
        <label className={styles.fieldLabel}>Steps</label>
        <Btn size="sm" variant="ghost" onClick={addStep}>+ Add step</Btn>
      </div>

      <div className={styles.editStepsList}>
        {steps.map((step, i) => (
          <div key={i} className={styles.editStep}>
            <div className={styles.editStepRow}>
              <span className={styles.stepNumber}>{i + 1}</span>
              <SelectField
                label="Action"
                value={step.action_type}
                onChange={(v) => updateStep(i, { action_type: v as PlanActionType })}
                options={ACTION_OPTIONS}
              />
              <TextField
                label="Target file"
                value={step.target_file_path}
                onChange={(v) => updateStep(i, { target_file_path: v })}
                placeholder={step.action_type === 'no_op' ? 'N/A' : 'path/to/file.py'}
              />
              <button
                type="button"
                className={styles.removeStepBtn}
                onClick={() => removeStep(i)}
                disabled={steps.length <= 1}
                title="Remove step"
              >
                ✕
              </button>
            </div>
            <textarea
              className={styles.editTextarea}
              value={step.description}
              onChange={(e) => updateStep(i, { description: e.target.value })}
              placeholder="What is being done in this step"
              rows={2}
            />
            <textarea
              className={styles.editTextarea}
              value={step.explanation}
              onChange={(e) => updateStep(i, { explanation: e.target.value })}
              placeholder="Why this step is necessary"
              rows={2}
            />
          </div>
        ))}
      </div>
    </Modal>
  )
}