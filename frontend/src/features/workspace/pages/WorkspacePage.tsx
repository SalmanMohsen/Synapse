import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { AppShell, shellStyles as s } from '@/shared/components/AppShell'
import {
  EmptyState, SpinnerPage, Badge, Modal, TextField, Btn, ConfirmDialog,
} from '@/shared/components'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useWorkspace, useWorkspaceMembers } from '../hooks/useWorkspaces'
import { useProjects, useCreateProject } from '@/features/project/hooks/useProjects'
import type { Project } from '@/features/project/types/project.types'

export default function WorkspacePage() {
  const { wid } = useParams<{ wid: string }>()
  const { data: workspace, isLoading: wsLoading } = useWorkspace(wid!)
  const { data: members } = useWorkspaceMembers(wid!)
  const user = useAuthStore((s) => s.user)
  const [showCreate, setShowCreate] = useState(false)

  const myMembership = members?.find((m) => m.user_id === user?.id)
  const isOwner = myMembership?.is_owner ?? false
  const canCreateProject = isOwner || workspace?.project_creation_policy === 'open'

  if (wsLoading) return <AppShell><SpinnerPage /></AppShell>
  if (!workspace) return <AppShell><EmptyState icon="○" title="Workspace not found" /></AppShell>

  return (
    <AppShell
      breadcrumbs={[
        { label: 'Workspaces', href: '/' },
        { label: workspace.name },
      ]}
    >
      <div className={s.sectionHead}>
        <div>
          <h1 className={s.pageTitle}>{workspace.name}</h1>
          <p className={s.pageMeta}>
            <Badge variant={workspace.project_creation_policy === 'open' ? 'success' : 'default'}>
              {workspace.project_creation_policy === 'open' ? 'Open' : 'Restricted'}
            </Badge>
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {isOwner && (
            <Btn variant="ghost" onClick={() => {}}>
              <Link to={`/workspaces/${wid}/settings`} style={{ textDecoration: 'none', color: 'inherit', display: 'flex', alignItems: 'center', gap: 6 }}>
                <GearIcon /> Settings
              </Link>
            </Btn>
          )}
          {canCreateProject && (
            <Btn variant="primary" onClick={() => setShowCreate(true)}>
              <PlusIcon /> New project
            </Btn>
          )}
        </div>
      </div>

      <ProjectList workspaceId={wid!} canCreate={canCreateProject} onNew={() => setShowCreate(true)} />

      {showCreate && (
        <CreateProjectModal workspaceId={wid!} onClose={() => setShowCreate(false)} />
      )}
    </AppShell>
  )
}

function ProjectList({
  workspaceId,
  canCreate,
  onNew,
}: {
  workspaceId: string
  canCreate: boolean
  onNew: () => void
}) {
  const { data: projects, isLoading } = useProjects(workspaceId)
  const navigate = useNavigate()

  if (isLoading) return <SpinnerPage />
  if (!projects?.length) {
    return (
      <EmptyState
        icon="⊹"
        title="No projects yet"
        body="Create a project to start organising your team's work."
        action={canCreate ? <Btn variant="primary" onClick={onNew}>Create project</Btn> : undefined}
      />
    )
  }

  return (
    <div className={s.cardGrid}>
      {projects.map((p) => (
        <ProjectCard key={p.id} project={p} onClick={() => navigate(`/projects/${p.id}`)} />
      ))}
    </div>
  )
}

function ProjectCard({ project, onClick }: { project: Project; onClick: () => void }) {
  return (
    <div
      className={s.card}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
    >
      <p className={s.cardName}>{project.name}</p>
      <div className={s.cardMeta}>
        <span className={s.cardMetaText}>{project.default_branch}</span>
        {project.github_app_installation_id && (
          <Badge variant="success">GitHub</Badge>
        )}
      </div>
    </div>
  )
}

function CreateProjectModal({ workspaceId, onClose }: { workspaceId: string; onClose: () => void }) {
  const navigate = useNavigate()
  const create = useCreateProject(workspaceId)
  const [name, setName] = useState('')
  const [branch, setBranch] = useState('main')
  const [nameErr, setNameErr] = useState('')

  const handleSubmit = async () => {
    if (!name.trim() || name.trim().length < 2) {
      setNameErr('Name must be at least 2 characters')
      return
    }
    const p = await create.mutateAsync({ name: name.trim(), default_branch: branch.trim() || 'main' })
    onClose()
    navigate(`/projects/${p.id}`)
  }

  return (
    <Modal
      title="New project"
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleSubmit} loading={create.isPending}>Create</Btn>
        </>
      }
    >
      <TextField
        label="Project name"
        value={name}
        onChange={(v) => { setName(v); setNameErr('') }}
        placeholder="my-app"
        error={nameErr}
        autoFocus
      />
      <TextField
        label="Default branch"
        value={branch}
        onChange={setBranch}
        placeholder="main"
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

function GearIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="2.5" />
      <path d="M8 1.5v1M8 13.5v1M1.5 8h1M13.5 8h1M3.2 3.2l.7.7M12.1 12.1l.7.7M12.8 3.2l-.7.7M3.9 12.1l-.7.7" />
    </svg>
  )
}