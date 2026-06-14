import {
  useState, useRef, useEffect, useCallback, type KeyboardEvent,
} from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { AppShell } from '@/shared/components/AppShell'
import { SpinnerPage, EmptyState, Btn, Modal, SelectField } from '@/shared/components' // <-- Import Modal & SelectField
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useChannel, useChannelMembers, useChannels } from '@/features/channel/hooks/useChannels' // <-- Import useChannels
import { useProjectMembers } from '@/features/project/hooks/useProjects'
import {
  useTicketDetail, useActivateTicket, useDeactivateTicket, useRouteTicket, // <-- Import useRouteTicket
} from '../hooks/useTickets'
import { useMessages, useSendMessage, useEditMessage, useDeleteMessage } from '@/features/message/hooks/useMessages'
import type { TicketRead, TicketStatus, TicketPriority } from '../types/ticket.types'
import { STATUS_LABELS, PRIORITY_LABELS } from '../types/ticket.types'
import type { MessageRead } from '@/features/message/types/message.types'
import type { MessageListResponse } from '@/features/message/types/message.types'
import styles from './TicketDetailPage.module.css'

// ── Helpers ──
function timeAgo(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 60)  return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

const STATUS_CLASS: Record<TicketStatus, string> = {
  backlog:           styles.statusBacklog,
  routed:            styles.statusBacklog, // styled same as backlog
  active:            styles.statusActive,
  in_discussion:     styles.statusDiscussion,
  consensus_reached: styles.statusConsensus,
  plan_review:       styles.statusPlanReview,
  agent_working:     styles.statusAgentWorking,
  in_review:         styles.statusInReview,
  merged:            styles.statusMerged,
  closed:            styles.statusClosed,
}

function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`${styles.statusBadge} ${STATUS_CLASS[status]}`}>
      <span className={styles.statusDot} />
      {STATUS_LABELS[status]}
    </span>
  )
}

function PriorityBadge({ priority }: { priority: TicketPriority }) {
  const extra = priority === 'high' ? styles.priorityHigh
    : priority === 'critical' ? styles.priorityCritical
    : ''
  return (
    <span className={`${styles.priorityBadge} ${extra}`}>
      {PRIORITY_LABELS[priority]}
    </span>
  )
}

// ── Page ──
export default function TicketDetailPage() {
  const { tid } = useParams<{ tid: string }>()
  const { data, isLoading } = useTicketDetail(tid!)
  const qc = useQueryClient()

  useEffect(() => {
    if (!data || !tid) return
    const existing = qc.getQueryData(['messages', tid])
    if (existing) return
    qc.setQueryData(['messages', tid], {
      pages: [data.messages as MessageListResponse],
      pageParams: [undefined],
    })
  }, [data, tid, qc])

  if (isLoading) return <AppShell><SpinnerPage /></AppShell>
  if (!data) return (
    <AppShell>
      <EmptyState icon="○" title="Ticket not found" />
    </AppShell>
  )

  const { ticket, thread_state } = data

  return (
    <TicketView ticket={ticket} threadSummary={thread_state?.rolling_summary ?? null} />
  )
}

// ── TicketView ──
function TicketView({
  ticket,
  threadSummary,
}: {
  ticket: TicketRead
  threadSummary: string | null
}) {
  const { data: channel } = useChannel(ticket.channel_id)
  const { data: channelMembers } = useChannelMembers(ticket.channel_id)
  const { data: projectMembers } = useProjectMembers(channel?.project_id ?? '')
  const { data: channels } = useChannels(channel?.project_id ?? '') // <-- Fetch project channels
  const user = useAuthStore((s) => s.user)

  const myProjectMember = projectMembers?.find((m) => m.user_id === user?.id)
  const isTeamLead = myProjectMember?.role === 'team_lead'

  const myChannelMember = channelMembers?.find((m) => m.user_id === user?.id)
  const isChannelLead = myChannelMember?.role === 'channel_lead'

  const isLocked = ['backlog', 'routed'].includes(ticket.status) && !channel?.is_leads_channel

  const activate   = useActivateTicket(ticket.id, ticket.channel_id)
  const route      = useRouteTicket(ticket.id)

  const [showRoute, setShowRoute] = useState(false)
  const [selectedChannelId, setSelectedChannelId] = useState('')

  const handleRouteSave = async () => {
    if (!selectedChannelId) return
    await route.mutateAsync({ channel_id: selectedChannelId })
    setShowRoute(false)
  }

  // Only allow routing to discipline channels (exclude the leads channel)
  const disciplineChannels = channels?.filter((c) => !c.is_leads_channel) ?? []

  return (
    <AppShell
      breadcrumbs={[
        { label: 'Workspaces', href: '/' },
        ...(channel ? [
          { label: 'Project', href: `/projects/${channel.project_id}` },
          { label: channel.name, href: `/channels/${ticket.channel_id}` },
        ] : []),
        { label: ticket.title },
      ]}
    >
      <div className={styles.page}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerTop}>
            <h1 className={styles.title}>{ticket.title}</h1>
          </div>
          <div className={styles.headerMeta}>
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            <span className={styles.metaSep}>·</span>
            <span className={styles.metaText}>
              opened {timeAgo(ticket.created_at)}
            </span>
          </div>
        </div>

        {/* Body */}
        <div className={styles.body}>
          {/* Left sidebar */}
          <aside className={styles.sidebar}>
            <div className={styles.sideSection}>
              <p className={styles.sideSectionTitle}>Description</p>
              {ticket.description ? (
                <p className={styles.description}>{ticket.description}</p>
              ) : (
                <p className={styles.noDescription}>No description</p>
              )}
            </div>

            <div className={styles.sideSection}>
              <p className={styles.sideSectionTitle}>Details</p>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>Status</span>
                <StatusBadge status={ticket.status} />
              </div>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>Priority</span>
                <PriorityBadge priority={ticket.priority} />
              </div>
            </div>

            {threadSummary && (
              <div className={styles.sideSection}>
                <p className={styles.sideSectionTitle}>AI summary</p>
                <div className={styles.summaryCard}>
                  <p className={styles.summaryText}>{threadSummary}</p>
                </div>
              </div>
            )}

            {/* Actions Panel */}
            {(isTeamLead || isChannelLead) && (
              <div className={styles.sideSection}>
                <p className={styles.sideSectionTitle}>Actions</p>
                <div className={styles.actionGroup}>
                  {/* Route Button — only shown to Team Leads on backlog/routed tickets */}
                  {['backlog', 'routed'].includes(ticket.status) && isTeamLead && (
                    <button
                      className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                      onClick={() => {
                        setSelectedChannelId(disciplineChannels[0]?.id ?? '')
                        setShowRoute(true)
                      }}
                    >
                      Route ticket
                    </button>
                  )}

                  {/* Activate Button — only shown to Channel Leads on routed tickets */}
                  {ticket.status === 'routed' && isChannelLead && (
                    <button
                      className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                      onClick={() => activate.mutate()}
                      disabled={activate.isPending}
                    >
                      {activate.isPending ? 'Activating…' : 'Activate ticket'}
                    </button>
                  )}
                  <Link
                    to={`/channels/${ticket.channel_id}`}
                    className={styles.actionBtn}
                    style={{ textDecoration: 'none', display: 'flex', alignItems: 'center' }}
                  >
                    ← Back to channel
                  </Link>
                </div>
              </div>
            )}
          </aside>

          {/* Thread Panel */}
          <ThreadPanel ticketId={ticket.id} isLocked={isLocked} />
        </div>
      </div>

      {/* Routing Destination Selection Modal */}
      {showRoute && (
        <Modal
          title="Route Ticket to Discipline Channel"
          onClose={() => setShowRoute(false)}
          footer={
            <>
              <Btn variant="ghost" onClick={() => setShowRoute(false)}>Cancel</Btn>
              <Btn variant="primary" onClick={handleRouteSave} loading={route.isPending}>
                Route Ticket
              </Btn>
            </>
          }
        >
          <SelectField
            label="Destination Channel"
            value={selectedChannelId}
            onChange={setSelectedChannelId}
            options={disciplineChannels.map((c) => ({
              value: c.id,
              label: c.name,
            }))}
          />
        </Modal>
      )}
    </AppShell>
  )
}

// ── ThreadPanel ──
function ThreadPanel({ ticketId, isLocked }: { ticketId: string; isLocked: boolean }) {
  const user = useAuthStore((s) => s.user)
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useMessages(ticketId)
  const send = useSendMessage(ticketId)
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isFirstLoad = useRef(true)

  const allMessages: MessageRead[] = []
  if (data) {
    const reversed = [...data.pages].reverse()
    for (const page of reversed) {
      allMessages.push(...page.items)
    }
  }

  useEffect(() => {
    if (isFirstLoad.current && allMessages.length > 0) {
      isFirstLoad.current = false
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    }
  }, [allMessages.length])

  useEffect(() => {
    if (isFirstLoad.current) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [allMessages.length])

  const handleSend = useCallback(async () => {
    const content = draft.trim()
    if (!content || send.isPending || isLocked) return
    setDraft('')
    await send.mutateAsync({ content })
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }, [draft, send, isLocked])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSend()
    }
  }

  const handleTextareaChange = (v: string) => {
    setDraft(v)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`
    }
  }

  return (
    <div className={styles.thread}>
      <div className={styles.messageList}>
        {hasNextPage && (
          <div className={styles.loadEarlier}>
            <button
              className={styles.loadEarlierBtn}
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
            >
              {isFetchingNextPage ? 'Loading…' : 'Load earlier messages'}
            </button>
          </div>
        )}

        {allMessages.length === 0 && (
          <div style={{ margin: 'auto', paddingTop: 40, textAlign: 'center' }}>
            <p style={{ color: 'var(--text-disabled)', fontSize: 13 }}>
              No messages yet. Start the discussion.
            </p>
          </div>
        )}

        {allMessages.map((msg) => (
          <MessageItem
            key={msg.id}
            message={msg}
            ticketId={ticketId}
            isOwn={msg.author_id === user?.id}
          />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className={styles.inputArea}>
        <div className={styles.inputWrap}>
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            value={draft}
            onChange={(e) => handleTextareaChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isLocked ? "This thread is locked until activated..." : "Write a message…"}
            rows={1}
            disabled={isLocked}
          />
          <button
            className={styles.sendBtn}
            onClick={handleSend}
            disabled={isLocked || !draft.trim() || send.isPending}
            aria-label="Send"
          >
            <SendIcon />
          </button>
        </div>
        <p className={styles.inputHint}>
          {isLocked ? "Only the Channel Lead can activate and unlock this thread." : "⌘ + Enter to send"}
        </p>
      </div>
    </div>
  )
}

// ── MessageItem ──
function MessageItem({
  message,
  ticketId,
  isOwn,
}: {
  message: MessageRead
  ticketId: string
  isOwn: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState(message.content ?? '')
  const editMsg   = useEditMessage(ticketId)
  const deleteMsg = useDeleteMessage(ticketId)

  if (message.type !== 'human') {
    return (
      <div className={styles.systemMessage}>
        <span className={styles.systemIcon}>⬡</span>
        <span>{message.content ?? 'Agent event'}</span>
      </div>
    )
  }

  const authorInitial = message.author?.display_name?.[0]?.toUpperCase() ?? '?'

  const handleSaveEdit = async () => {
    if (!editDraft.trim()) return
    await editMsg.mutateAsync({ messageId: message.id, data: { content: editDraft.trim() } })
    setEditing(false)
  }

  const handleDelete = () => {
    deleteMsg.mutate(message.id)
  }

  return (
    <div className={styles.messageGroup}>
      {message.author?.avatar_url ? (
        <img src={message.author.avatar_url} alt="" className={styles.avatarImg} />
      ) : (
        <div className={styles.avatar}>{authorInitial}</div>
      )}

      <div className={styles.messageBody}>
        <div className={styles.messageHeader}>
          <span className={styles.authorName}>
            {message.author?.display_name ?? 'Unknown'}
          </span>
          <span className={styles.messageTime}>{timeAgo(message.created_at)}</span>
          {message.edited_at && !message.deleted_at && (
            <span className={styles.editedBadge}>(edited)</span>
          )}
        </div>

        {message.deleted_at ? (
          <p className={styles.deletedContent}>This message was deleted.</p>
        ) : editing ? (
          <div>
            <textarea
              className={styles.editArea}
              value={editDraft}
              onChange={(e) => setEditDraft(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSaveEdit()
                if (e.key === 'Escape') setEditing(false)
              }}
              autoFocus
            />
            <div className={styles.editActions}>
              <Btn size="sm" variant="primary" onClick={handleSaveEdit} loading={editMsg.isPending}>
                Save
              </Btn>
              <Btn size="sm" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Btn>
            </div>
          </div>
        ) : (
          <p className={styles.messageContent}>{message.content}</p>
        )}

        {!message.deleted_at && !editing && isOwn && (
          <div className={styles.messageActions}>
            <button
              className={styles.msgActionBtn}
              onClick={() => { setEditDraft(message.content ?? ''); setEditing(true) }}
            >
              Edit
            </button>
            <button
              className={`${styles.msgActionBtn} ${styles.msgActionBtnDanger}`}
              onClick={handleDelete}
              disabled={deleteMsg.isPending}
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2L2 6.5l5 2 2 5L14 2z" />
    </svg>
  )
}