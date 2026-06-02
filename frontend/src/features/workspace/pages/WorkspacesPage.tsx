import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AppShell, shellStyles as s } from '@/shared/components/AppShell'
import { EmptyState, SpinnerPage, Badge, Modal, TextField, Btn } from '@/shared/components'
import { useWorkspaces, useCreateWorkspace } from '../hooks/useWorkspaces'
import type { Workspace } from '../types/workspace.types'

export default function WorkspacesPage() {
  const { data: workspaces, isLoading } = useWorkspaces()
  const [showCreate, setShowCreate] = useState(false)

  return (
    <AppShell>
      <div className={s.sectionHead}>
        <div>
          <h1 className={s.pageTitle}>Workspaces</h1>
          <p className={s.pageMeta}>Your collaborative environments</p>
        </div>
        <Btn variant="primary" onClick={() => setShowCreate(true)}>
          <PlusIcon /> New workspace
        </Btn>
      </div>

      {isLoading ? (
        <SpinnerPage />
      ) : !workspaces?.length ? (
        <EmptyState
          icon="⬡"
          title="No workspaces yet"
          body="Create your first workspace to start collaborating with your team."
          action={
            <Btn variant="primary" onClick={() => setShowCreate(true)}>
              Create workspace
            </Btn>
          }
        />
      ) : (
        <div className={s.cardGrid}>
          {workspaces.map((ws) => (
            <WorkspaceCard key={ws.id} workspace={ws} />
          ))}
        </div>
      )}

      {showCreate && <CreateWorkspaceModal onClose={() => setShowCreate(false)} />}
    </AppShell>
  )
}

function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  const navigate = useNavigate()
  return (
    <div
      className={s.card}
      onClick={() => navigate(`/workspaces/${workspace.id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/workspaces/${workspace.id}`)}
    >
      <p className={s.cardName}>{workspace.name}</p>
      <div className={s.cardMeta}>
        <Badge variant={workspace.project_creation_policy === 'open' ? 'success' : 'default'}>
          {workspace.project_creation_policy === 'open' ? 'Open' : 'Restricted'}
        </Badge>
        <span className={s.cardMetaText}>
          {new Date(workspace.created_at).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
        </span>
      </div>
    </div>
  )
}

function CreateWorkspaceModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const create = useCreateWorkspace()
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    if (!name.trim() || name.trim().length < 2) {
      setError('Name must be at least 2 characters')
      return
    }
    const ws = await create.mutateAsync({ name: name.trim() })
    onClose()
    navigate(`/workspaces/${ws.id}`)
  }

  return (
    <Modal
      title="New workspace"
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleSubmit} loading={create.isPending}>
            Create
          </Btn>
        </>
      }
    >
      <TextField
        label="Workspace name"
        value={name}
        onChange={(v) => { setName(v); setError('') }}
        placeholder="Acme Corp"
        error={error}
        autoFocus
      />
    </Modal>
  )
}

function PlusIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M8 2v12M2 8h12" />
    </svg>
  )
}