import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AppShell, shellStyles as s } from '@/shared/components/AppShell'
import {
  SpinnerPage, EmptyState, Badge, DisciplineBadge, MemberRow,
  Btn, ConfirmDialog, Modal, TextField, SelectField,
} from '@/shared/components'
import { useAuthStore } from '@/features/auth/store/authSlice'
import {
  useChannel, useChannelMembers, useAddChannelMember,
  useUpdateChannelMember, useRemoveChannelMember,
} from '../hooks/useChannels'
import { useProjectMembers } from '@/features/project/hooks/useProjects'
import { AddMemberInlineForm } from './AddMemberInlineForm'
import { useTickets, useCreateTicket } from '@/features/ticket/hooks/useTickets'
import type { TicketRead, TicketPriority } from '@/features/ticket/types/ticket.types'
import { STATUS_LABELS, PRIORITY_LABELS } from '@/features/ticket/types/ticket.types'
import type { ChannelMemberRole } from '../types/channel.types'

const CHANNEL_ROLES: { value: ChannelMemberRole; label: string }[] = [
  { value: 'channel_lead', label: 'Channel Lead' },
  { value: 'member',        label: 'Member' },
]

type Tab = 'tickets' | 'members'

export default function ChannelPage() {
  const { cid } = useParams<{ cid: string }>()
  const { data: channel, isLoading: chLoading } = useChannel(cid!)
  const { data: channelMembers } = useChannelMembers(cid!)
  const { data: projectMembers } = useProjectMembers(channel?.project_id ?? '')
  const user = useAuthStore((s) => s.user)

  const myChannelMember = channelMembers?.find((m) => m.user_id === user?.id)
  const myProjectMember = projectMembers?.find((m) => m.user_id === user?.id)
  const isChannelLead  = myChannelMember?.role === 'channel_lead'
  const isProjectLead  = myProjectMember?.role === 'team_lead'
  const canManage = (isChannelLead || isProjectLead) && !channel?.is_leads_channel

  const addMember    = useAddChannelMember(cid!)
  const updateMember = useUpdateChannelMember(cid!)
  const removeMember = useRemoveChannelMember(cid!)

  const [tab, setTab]           = useState<Tab>('tickets')
  const [showAdd, setShowAdd]   = useState(false)
  const [removeTarget, setRemoveTarget] = useState<string | null>(null)
  const [showCreate, setShowCreate]     = useState(false)

  if (chLoading) return <AppShell><SpinnerPage /></AppShell>
  if (!channel)  return <AppShell><EmptyState icon="○" title="Channel not found" /></AppShell>

  return (
    <AppShell
      breadcrumbs={[
        { label: 'Workspaces', href: '/' },
        { label: 'Project',     href: `/projects/${channel.project_id}` },
        { label: channel.name },
      ]}
    >
      {/* ── Header ── */}
      <div className={s.sectionHead}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h1 className={s.pageTitle}>{channel.name}</h1>
          {!channel.is_leads_channel && channel.discipline && (
            <DisciplineBadge discipline={channel.discipline} />
          )}
          {channel.is_leads_channel && <Badge variant="brand">Leads</Badge>}
        </div>
        {tab === 'tickets' && !channel.is_leads_channel && (
          <Btn variant="primary" onClick={() => setShowCreate(true)}>
            New ticket
          </Btn>
        )}
      </div>

      {/* ── Tabs ── */}
      <div className={s.tabs}>
        <button
          className={`${s.tab} ${tab === 'tickets' ? s.tabActive : ''}`}
          onClick={() => setTab('tickets')}
        >
          Tickets
        </button>
        <button
          className={`${s.tab} ${tab === 'members' ? s.tabActive : ''}`}
          onClick={() => setTab('members')}
        >
          Members ({channelMembers?.length ?? 0})
        </button>
      </div>

      {/* ── Tickets tab ── */}
      {tab === 'tickets' && (
        <TicketList channelId={cid!} />
      )}

      {/* ── Members tab ── */}
      {tab === 'members' && (
        <div className={s.listPanel}>
          <div className={s.listPanelHeader}>
            <span className={s.listPanelTitle}>Members</span>
            {canManage && (
              <Btn size="sm" variant="ghost" onClick={() => setShowAdd(true)}>Add</Btn>
            )}
          </div>
          <div className={s.listPanelBody}>
            {!channelMembers?.length && <EmptyState icon="○" title="No members" />}
            {channelMembers?.map((m) => {
              const isMe     = m.user_id === user?.id
              const theirRank = m.role === 'channel_lead' ? 2 : 1
              const myRank   = isChannelLead ? 2 : isProjectLead ? 3 : 1
              const canAct   = canManage && !isMe && myRank > theirRank

              return (
                <MemberRow
                  key={m.id}
                  name={m.user?.display_name ?? m.user_id}
                  subtitle={m.user?.email}
                  badges={
                    <Badge variant={m.role === 'channel_lead' ? 'brand' : 'default'}>
                      {m.role === 'channel_lead' ? 'Lead' : 'Member'}
                    </Badge>
                  }
                  actions={
                    canAct ? (
                      <>
                        {m.role !== 'channel_lead' && (
                          <Btn
                            size="sm"
                            variant="ghost"
                            onClick={() => updateMember.mutate({ userId: m.user_id, data: { role: 'channel_lead' } })}
                            loading={updateMember.isPending}
                          >
                            Promote
                          </Btn>
                        )}
                        <Btn
                          size="sm"
                          variant="danger"
                          onClick={() => setRemoveTarget(m.user_id)}
                        >
                          Remove
                        </Btn>
                      </>
                    ) : undefined
                  }
                />
              )
            })}
          </div>
        </div>
      )}

      {/* ── Modals ── */}
      {showAdd && (
        <AddMemberInlineForm
          roles={CHANNEL_ROLES}
          onAdd={async (userId, role) => {
            await addMember.mutateAsync({ user_id: userId, role: role as ChannelMemberRole })
            setShowAdd(false)
          }}
          onClose={() => setShowAdd(false)}
          loading={addMember.isPending}
          scopeKey={`project-${channel.project_id}`}
          searchFn={async (q) => {
            const lowerQ = q.toLowerCase()
            return (projectMembers ?? [])
              .filter((m) => m.user && (
                m.user.display_name.toLowerCase().includes(lowerQ) ||
                m.user.email.toLowerCase().includes(lowerQ)
              ))
              .map((m) => m.user!)
          }}
        />
      )}

      {showCreate && (
        <CreateTicketModal
          channelId={cid!}
          onClose={() => setShowCreate(false)}
        />
      )}

      {removeTarget && (
        <ConfirmDialog
          title="Remove member"
          body="Remove this member from the channel?"
          confirmLabel="Remove"
          danger
          onConfirm={() => { removeMember.mutate(removeTarget); setRemoveTarget(null) }}
          onClose={() => setRemoveTarget(null)}
          loading={removeMember.isPending}
        />
      )}
    </AppShell>
  )
}

// ── TicketList ────────────────────────────────────────────────────────────────

function TicketList({ channelId }: { channelId: string }) {
  const { data: tickets, isLoading } = useTickets(channelId)
  const navigate = useNavigate()

  if (isLoading) return <SpinnerPage />

  if (!tickets?.length) {
    return (
      <EmptyState
        icon="⊹"
        title="No tickets yet"
        body="Create a ticket to start a discussion thread."
      />
    )
  }

  // Group by status
  const backlog  = tickets.filter((t) => t.status === 'backlog')
  const active   = tickets.filter((t) => !['backlog', 'closed', 'merged'].includes(t.status))
  const closed   = tickets.filter((t) => ['closed', 'merged'].includes(t.status))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {active.length > 0 && (
        <TicketGroup
          label="Active"
          tickets={active}
          onOpen={(id) => navigate(`/tickets/${id}`)}
        />
      )}
      {backlog.length > 0 && (
        <TicketGroup
          label="Backlog"
          tickets={backlog}
          onOpen={(id) => navigate(`/tickets/${id}`)}
        />
      )}
      {closed.length > 0 && (
        <TicketGroup
          label="Closed"
          tickets={closed}
          onOpen={(id) => navigate(`/tickets/${id}`)}
          muted
        />
      )}
    </div>
  )
}

function TicketGroup({
  label,
  tickets,
  onOpen,
  muted = false,
}: {
  label: string
  tickets: TicketRead[]
  onOpen: (id: string) => void
  muted?: boolean
}) {
  return (
    <div className={s.listPanel}>
      <div className={s.listPanelHeader}>
        <span className={s.listPanelTitle} style={muted ? { opacity: 0.5 } : undefined}>
          {label} · {tickets.length}
        </span>
      </div>
      <div className={s.listPanelBody}>
        {tickets.map((ticket) => (
          <TicketRow key={ticket.id} ticket={ticket} onOpen={onOpen} />
        ))}
      </div>
    </div>
  )
}

function TicketRow({ ticket, onOpen }: { ticket: TicketRead; onOpen: (id: string) => void }) {
  const statusColor = STATUS_COLOR_INLINE[ticket.status] ?? 'var(--text-disabled)'

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(ticket.id)}
      onKeyDown={(e) => e.key === 'Enter' && onOpen(ticket.id)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 0',
        borderBottom: '1px solid var(--border-subtle)',
        cursor: 'pointer',
      }}
    >
      {/* Status dot */}
      <span style={{
        width: 8, height: 8, borderRadius: '50%',
        background: statusColor, flexShrink: 0,
      }} />

      {/* Title */}
      <span style={{
        flex: 1, fontSize: 13.5, color: 'var(--text-primary)',
        fontWeight: 400, minWidth: 0, overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {ticket.title}
      </span>

      {/* Status label */}
      <span style={{
        fontSize: 11, color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-mono)', flexShrink: 0,
      }}>
        {STATUS_LABELS[ticket.status]}
      </span>

      {/* Priority */}
      <span style={{
        fontSize: 11, color: 'var(--text-disabled)',
        fontFamily: 'var(--font-mono)', flexShrink: 0,
      }}>
        {PRIORITY_LABELS[ticket.priority]}
      </span>
    </div>
  )
}

const STATUS_COLOR_INLINE: Partial<Record<string, string>> = {
  backlog:           'var(--text-disabled)',
  active:            'var(--brand)',
  in_discussion:     '#3b82f6',
  consensus_reached: '#8b5cf6',
  plan_review:       '#f59e0b',
  agent_working:     '#f59e0b',
  in_review:         '#22c55e',
  merged:            '#22c55e',
  closed:            'var(--text-disabled)',
}

// ── CreateTicketModal ─────────────────────────────────────────────────────────

const PRIORITY_OPTIONS: { value: TicketPriority; label: string }[] = [
  { value: 'low',      label: 'Low' },
  { value: 'medium',   label: 'Medium' },
  { value: 'high',     label: 'High' },
  { value: 'critical', label: 'Critical' },
]

function CreateTicketModal({
  channelId,
  onClose,
}: {
  channelId: string
  onClose: () => void
}) {
  const navigate = useNavigate()
  const create = useCreateTicket(channelId)
  const [title, setTitle]       = useState('')
  const [description, setDesc]  = useState('')
  const [priority, setPriority] = useState<TicketPriority>('medium')
  const [titleErr, setTitleErr] = useState('')

  const handleCreate = async () => {
    if (!title.trim()) { setTitleErr('Title is required'); return }
    const ticket = await create.mutateAsync({
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
    })
    onClose()
    navigate(`/tickets/${ticket.id}`)
  }

  return (
    <Modal
      title="New ticket"
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleCreate} loading={create.isPending}>
            Create
          </Btn>
        </>
      }
    >
      <TextField
        label="Title"
        value={title}
        onChange={(v) => { setTitle(v); setTitleErr('') }}
        placeholder="Implement JWT refresh logic"
        error={titleErr}
        autoFocus
      />
      <TextField
        label="Description (optional)"
        value={description}
        onChange={setDesc}
        placeholder="Context, links, or relevant details…"
        multiline
      />
      <SelectField
        label="Priority"
        value={priority}
        onChange={(v) => setPriority(v as TicketPriority)}
        options={PRIORITY_OPTIONS}
      />
    </Modal>
  )
}