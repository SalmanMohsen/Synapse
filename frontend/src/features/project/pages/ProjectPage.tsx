import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { AppShell, shellStyles as s } from '@/shared/components/AppShell'
import { api } from '@/shared/lib/axios' 
import type { WorkspaceMember } from '@/features/workspace/types/workspace.types'
import {
  SpinnerPage, EmptyState, Badge, DisciplineBadge, MemberRow,
  Modal, SelectField, ToggleField, Btn, ConfirmDialog, UserSearchField, TextField
} from '@/shared/components'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useProject, useProjectMembers, useAddProjectMember, useUpdateProjectMember, useRemoveProjectMember } from '../hooks/useProjects'
import { useWorkspaceMembers } from '@/features/workspace/hooks/useWorkspaces'
import { useChannels, useCreateChannel } from '@/features/channel/hooks/useChannels'
import { useSendProjectInvite } from '@/features/inbox/hooks/useInbox'
import { InviteModal } from '@/features/workspace/pages/WorkspaceSettingsPage'
import type { Channel } from '@/features/channel/types/channel.types'
import type { ProjectRole } from '../types/project.types'
import { DISCIPLINE_LABELS } from '@/shared/components'
import type { User } from '@/features/auth/types/auth.types'
type Tab = 'channels' | 'members'

const DISCIPLINES = Object.entries(DISCIPLINE_LABELS).map(([value, label]) => ({ value, label }))
const PROJECT_ROLES: { value: ProjectRole; label: string }[] = [
  { value: 'team_lead', label: 'Team Lead' },
  { value: 'member', label: 'Member' },
  { value: 'advisor', label: 'Advisor' },
  { value: 'viewer', label: 'Viewer' },
]

export default function ProjectPage() {
    const { pid } = useParams<{ pid: string }>()
  const { data: project, isLoading: projLoading } = useProject(pid!)
  const { data: members, isLoading: memLoading } = useProjectMembers(pid!)
  const { data: workspaceMembers, isLoading: wsLoading } = useWorkspaceMembers(project?.workspace_id ?? '')
  const user = useAuthStore((s) => s.user)
  const [tab, setTab] = useState<Tab>('channels')

  if (projLoading || memLoading || wsLoading) return <AppShell><SpinnerPage /></AppShell>
  if (!project) return <AppShell><EmptyState icon="○" title="Project not found" /></AppShell>

  const myMember = members?.find((m) => m.user_id === user?.id)
  const isLead = myMember?.role === 'team_lead'
  
  // ADD THIS: Compute workspace ownership permissions
  const myWsMember = workspaceMembers?.find((m) => m.user_id === user?.id)
  const isWorkspaceOwner = myWsMember?.is_owner ?? false
  const canSeeSettings = isLead || isWorkspaceOwner

  return (
    <AppShell
      breadcrumbs={[
        { label: 'Workspaces', href: '/' },
        { label: 'Workspace', href: `/workspaces/${project.workspace_id}` },
        { label: project.name },
      ]}
    >
      <div className={s.sectionHead}>
        <div>
          <h1 className={s.pageTitle}>{project.name}</h1>
          <p className={s.pageMeta}>{project.default_branch}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {canSeeSettings && (
            <Link to={`/projects/${pid}/settings`} style={{ textDecoration: 'none' }}>
              <Btn variant="ghost"><GearIcon /> Settings</Btn>
            </Link>
          )}
        </div>
      </div>

      <div className={s.tabs}>
        <button className={`${s.tab} ${tab === 'channels' ? s.tabActive : ''}`} onClick={() => setTab('channels')}>
          Channels
        </button>
        <button className={`${s.tab} ${tab === 'members' ? s.tabActive : ''}`} onClick={() => setTab('members')}>
          Members {members && `(${members.length})`}
        </button>
      </div>

      {tab === 'channels' && <ChannelsTab projectId={pid!} isLead={isLead} />}
      {tab === 'members' && (<MembersTab projectId={pid!} workspaceId={project.workspace_id} isLead={isLead} members={members ?? []} myRole={myMember?.role} />)}
    </AppShell>
  )
}

// ── Channels tab ──────────────────────────────────────────────────────────────

function ChannelsTab({ projectId, isLead }: { projectId: string; isLead: boolean }) {
  const { data: channels, isLoading } = useChannels(projectId)
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)

  if (isLoading) return <SpinnerPage />

  const leadsChannel = channels?.find((c) => c.is_leads_channel)
  const disciplineChannels = channels?.filter((c) => !c.is_leads_channel) ?? []

  return (
    <>
      <div className={s.sectionHead}>
        <span className={s.sectionTitle}>Channels</span>
        {isLead && (
          <Btn variant="primary" size="sm" onClick={() => setShowCreate(true)}>
            <PlusIcon /> New channel
          </Btn>
        )}
      </div>

      {!channels?.length ? (
        <EmptyState
          icon="◈"
          title="No channels yet"
          body="Create discipline channels to organise your team's work."
          action={isLead ? <Btn variant="primary" onClick={() => setShowCreate(true)}>Create channel</Btn> : undefined}
        />
      ) : (
        <div className={s.cardGrid}>
          {leadsChannel && (
            <ChannelCard
              channel={leadsChannel}
              onClick={() => navigate(`/channels/${leadsChannel.id}`)}
            />
          )}
          {disciplineChannels.map((ch) => (
            <ChannelCard
              key={ch.id}
              channel={ch}
              onClick={() => navigate(`/channels/${ch.id}`)}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateChannelModal projectId={projectId} onClose={() => setShowCreate(false)} />
      )}
    </>
  )
}

function ChannelCard({ channel, onClick }: { channel: Channel; onClick: () => void }) {
  return (
    <div
      className={s.card}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <p className={s.cardName}>{channel.name}</p>
        {channel.is_leads_channel && <Badge variant="brand">Leads</Badge>}
      </div>
      <div className={s.cardMeta}>
        {channel.discipline && <DisciplineBadge discipline={channel.discipline} />}
        <span className={s.cardMetaText}>
          {channel.approval_policy === 'lead_only' ? 'Lead approval' : 'Any member'}
        </span>
      </div>
    </div>
  )
}

function CreateChannelModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const navigate = useNavigate()
  const create = useCreateChannel(projectId)
  const [name, setName] = useState('')
  const [discipline, setDiscipline] = useState('frontend')
  const [leadOnly, setLeadOnly] = useState(true)
  const [nameErr, setNameErr] = useState('')

  const handleSubmit = async () => {
    if (!name.trim() || name.trim().length < 2) { setNameErr('At least 2 characters'); return }
    const ch = await create.mutateAsync({
      name: name.trim(),
      discipline: discipline as any,
      approval_policy: leadOnly ? 'lead_only' : 'any_member',
    })
    onClose()
    navigate(`/channels/${ch.id}`)
  }

  return (
    <Modal
      title="New channel"
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleSubmit} loading={create.isPending}>Create</Btn>
        </>
      }
    >
      <TextField
        label="Channel name"
        value={name}
        onChange={(v) => { setName(v); setNameErr('') }}
        placeholder="api-layer"
        error={nameErr}
        autoFocus
      />
      <SelectField
        label="Discipline"
        value={discipline}
        onChange={setDiscipline}
        options={DISCIPLINES}
      />
      <ToggleField
        label="Lead-only approval"
        description="Only team leads can approve agent flows"
        checked={leadOnly}
        onChange={setLeadOnly}
      />
    </Modal>
  )
}

// ── Members tab ───────────────────────────────────────────────────────────────

function MembersTab({
  projectId,
  workspaceId,
  isLead,
  members,
  myRole,
}: {
  projectId: string
  workspaceId: string
  isLead: boolean
  members: ReturnType<typeof useProjectMembers>['data'] extends infer D ? NonNullable<D> : never
  myRole: ProjectRole | undefined
}) {
  const user = useAuthStore((s) => s.user)
  const updateMember = useUpdateProjectMember(projectId)
  const removeMember = useRemoveProjectMember(projectId)
  const sendInvite = useSendProjectInvite(projectId)
  const [showInvite, setShowInvite] = useState(false)
  const [removeTarget, setRemoveTarget] = useState<string | null>(null)

  const roleRank: Record<ProjectRole, number> = { team_lead: 3, member: 2, viewer: 1 , advisor: 1}
  const myRank = roleRank[myRole ?? 'viewer']

  return (
    <>
      <div className={s.sectionHead}>
        <span className={s.sectionTitle}>Members</span>
        {isLead && (
          <div style={{ display: 'flex', gap: 6 }}>
            <Btn size="sm" variant="ghost" onClick={() => setShowInvite(true)}>Invite member</Btn>
          </div>
        )}
      </div>

      <div className={s.listPanel}>
        <div className={s.listPanelBody}>
          {members.length === 0 && <EmptyState icon="○" title="No members" />}
          {members.map((m) => {
            const isMe = m.user_id === user?.id
            const theirRank = roleRank[m.role]
            const canAct = isLead && !isMe && myRank > theirRank

            return (
              <MemberRow
                key={m.id}
                name={m.user?.display_name ?? m.user_id}
                subtitle={m.user?.email}
                badges={<Badge variant={m.role === 'team_lead' ? 'brand' : 'default'}>{PROJECT_ROLE_LABELS[m.role]}</Badge>}
                actions={
                  canAct ? (
                    <>
                      <select
                        style={{ fontSize: 12, padding: '2px 6px', background: 'var(--bg-overlay)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', cursor: 'pointer' }}
                        value={m.role}
                        onChange={(e) => updateMember.mutate({ userId: m.user_id, data: { role: e.target.value as ProjectRole } })}
                      >
                        {PROJECT_ROLES.filter((r) => roleRank[r.value] < myRank).map((r) => (
                          <option key={r.value} value={r.value}>{r.label}</option>
                        ))}
                      </select>
                      <Btn size="sm" variant="danger" onClick={() => setRemoveTarget(m.user_id)}>Remove</Btn>
                    </>
                  ) : undefined
                }
              />
            )
          })}
        </div>
      </div>


      {showInvite && (
        <InviteModal
          title="Invite to project"
          roles={PROJECT_ROLES}
          onInvite={(userId, role) => sendInvite.mutateAsync({ target_user_id: userId, role }).then(() => setShowInvite(false))}
          onClose={() => setShowInvite(false)}
          loading={sendInvite.isPending}
          scopeKey={`workspace-${workspaceId}`} // <-- Scoped to workspace
          searchFn={async (q) => {
            // Fetch workspace members to filter against
            const res = await api.get<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`);
            const lowerQ = q.toLowerCase();
            return res.data
              .filter((m) => m.user && (
                m.user.display_name.toLowerCase().includes(lowerQ) ||
                m.user.email.toLowerCase().includes(lowerQ)
              ))
              .map((m) => m.user!);
          }}
        />
      )}

      {removeTarget && (
        <ConfirmDialog
          title="Remove member"
          body="Remove this member from the project?"
          confirmLabel="Remove"
          danger
          onConfirm={() => { removeMember.mutate(removeTarget); setRemoveTarget(null) }}
          onClose={() => setRemoveTarget(null)}
          loading={removeMember.isPending}
        />
      )}
    </>
  )
}


const PROJECT_ROLE_LABELS: Record<ProjectRole, string> = {
  team_lead: 'Team Lead',
  member: 'Member',
  advisor: 'Advisor',
  viewer: 'Viewer',
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