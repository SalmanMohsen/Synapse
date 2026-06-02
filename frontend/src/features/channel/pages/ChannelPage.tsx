import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { AppShell, shellStyles as s } from '@/shared/components/AppShell'
import {
  SpinnerPage, EmptyState, Badge, DisciplineBadge, MemberRow,
  Btn, ConfirmDialog,
} from '@/shared/components'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useChannel, useChannelMembers, useAddChannelMember, useUpdateChannelMember, useRemoveChannelMember } from '../hooks/useChannels'
import { useProjectMembers } from '@/features/project/hooks/useProjects'
import { AddMemberInlineForm } from './AddMemberInlineForm'
import type { ChannelMemberRole } from '../types/channel.types'

const CHANNEL_ROLES: { value: ChannelMemberRole; label: string }[] = [
  { value: 'channel_lead', label: 'Channel Lead' },
  { value: 'member', label: 'Member' },
]

export default function ChannelPage() {
  const { cid } = useParams<{ cid: string }>()
  const { data: channel, isLoading: chLoading } = useChannel(cid!)
  const { data: channelMembers } = useChannelMembers(cid!)
  const { data: projectMembers } = useProjectMembers(channel?.project_id ?? '')
  const user = useAuthStore((s) => s.user)

  const myChannelMember = channelMembers?.find((m) => m.user_id === user?.id)
  const myProjectMember = projectMembers?.find((m) => m.user_id === user?.id)
  const isChannelLead = myChannelMember?.role === 'channel_lead'
  const isProjectLead = myProjectMember?.role === 'team_lead'
  const canManage = (isChannelLead || isProjectLead) && !channel?.is_leads_channel
  const addMember = useAddChannelMember(cid!)
  const updateMember = useUpdateChannelMember(cid!)
  const removeMember = useRemoveChannelMember(cid!)

  const [showAdd, setShowAdd] = useState(false)
  const [removeTarget, setRemoveTarget] = useState<string | null>(null)

  if (chLoading) return <AppShell><SpinnerPage /></AppShell>
  if (!channel) return <AppShell><EmptyState icon="○" title="Channel not found" /></AppShell>

  return (
    <AppShell
      breadcrumbs={[
        { label: 'Workspaces', href: '/' },
        { label: 'Project', href: `/projects/${channel.project_id}` },
        { label: channel.name },
      ]}
    >
      {/* Header */}
      <div className={s.sectionHead}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h1 className={s.pageTitle}>{channel.name}</h1>
          {!channel.is_leads_channel && channel.discipline && (
            <DisciplineBadge discipline={channel.discipline} />
          )}
          {channel.is_leads_channel && <Badge variant="brand">Leads</Badge>}
        </div>
      </div>

      {/* Members panel */}
      <div style={{ marginBottom: 24 }}>
        <div className={s.listPanel}>
          <div className={s.listPanelHeader}>
            <span className={s.listPanelTitle}>Members ({channelMembers?.length ?? 0})</span>
            {canManage && (
              <div style={{ display: 'flex', gap: 6 }}>
                <Btn size="sm" variant="ghost" onClick={() => setShowAdd(true)}>Add</Btn>
              </div>
            )}
          </div>
          <div className={s.listPanelBody}>
            {!channelMembers?.length && <EmptyState icon="○" title="No members" />}
            {channelMembers?.map((m) => {
              const isMe = m.user_id === user?.id
              const theirRank = m.role === 'channel_lead' ? 2 : 1
              const myRank = isChannelLead ? 2 : isProjectLead ? 3 : 1
              const canAct = canManage && !isMe && myRank > theirRank

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
                        <Btn size="sm" variant="danger" onClick={() => setRemoveTarget(m.user_id)}>
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
      </div>

      {/* Ticket area stub */}
      <div className={s.listPanel}>
        <div className={s.listPanelHeader}>
          <span className={s.listPanelTitle}>Tickets</span>
        </div>
        <EmptyState
          icon="⊹"
          title="Tickets coming soon"
          body="The ticket and thread system will be available in Phase 2."
        />
      </div>

      {/* Modals */}
      {showAdd && (
        <AddMemberInlineForm
          roles={CHANNEL_ROLES}
          onAdd={async (userId, role) => {
            await addMember.mutateAsync({ user_id: userId, role: role as ChannelMemberRole })
            setShowAdd(false)
          }}
          onClose={() => setShowAdd(false)}
          loading={addMember.isPending}
          scopeKey={`project-${channel.project_id}`} // <-- Scoped to project
          searchFn={async (q) => {
            const lowerQ = q.toLowerCase();
            // Filter the already-fetched projectMembers array
            return (projectMembers ?? [])
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