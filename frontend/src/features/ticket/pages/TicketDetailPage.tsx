import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from "react";
import { useParams, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/shared/components/AppShell";
import {
  SpinnerPage,
  EmptyState,
  Btn,
  Modal,
  SelectField,
  TextField,
} from "@/shared/components"; // <-- Import TextField
import { useAuthStore } from "@/features/auth/store/authSlice";
import {
  useChannel,
  useChannelMembers,
  useChannels,
} from "@/features/channel/hooks/useChannels";
import { useProjectMembers } from "@/features/project/hooks/useProjects";
import {
  useTicketDetail,
  useActivateTicket,
  useDeactivateTicket,
  useRouteTicket,
  useSplitTicket,
  useGeneratePlan,
} from "../hooks/useTickets";
import {
  useMessages,
  useSendMessage,
  useEditMessage,
  useDeleteMessage,
} from "@/features/message/hooks/useMessages";
import { ticketApi } from "../api/ticketApi";
import type {
  TicketRead,
  TicketStatus,
  TicketPriority,
} from "../types/ticket.types";
import { STATUS_LABELS, PRIORITY_LABELS } from "../types/ticket.types";
import type { MessageRead } from "@/features/message/types/message.types";
import type { MessageListResponse } from "@/features/message/types/message.types";
import { toast } from "@/shared/hooks/useToast";
import styles from "./TicketDetailPage.module.css";
import { PlanCard } from "@/features/agenRun/components/PlanCard";
import { getPlanCardRunId } from "@/features/agenRun/utils";

// ── Types ──
interface ChildDraft {
  title: string;
  channelId: string;
  priority: TicketPriority;
}

// ── Helpers ──
function timeAgo(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

const STATUS_CLASS: Record<TicketStatus, string> = {
  backlog: styles.statusBacklog,
  routed: styles.statusBacklog,
  active: styles.statusActive,
  in_discussion: styles.statusDiscussion,
  consensus_reached: styles.statusConsensus,
  plan_review: styles.statusPlanReview,
  agent_working: styles.statusAgentWorking,
  in_review: styles.statusInReview,
  merged: styles.statusMerged,
  closed: styles.statusClosed,
  split: styles.statusClosed,
};

function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`${styles.statusBadge} ${STATUS_CLASS[status]}`}>
      <span className={styles.statusDot} />
      {STATUS_LABELS[status]}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: TicketPriority }) {
  const extra =
    priority === "high"
      ? styles.priorityHigh
      : priority === "critical"
        ? styles.priorityCritical
        : "";
  return (
    <span className={`${styles.priorityBadge} ${extra}`}>
      {PRIORITY_LABELS[priority]}
    </span>
  );
}

// ── Page ──
export default function TicketDetailPage() {
  const { tid } = useParams<{ tid: string }>();
  const { data, isLoading } = useTicketDetail(tid!);
  const qc = useQueryClient();

  useEffect(() => {
    if (!data || !tid) return;
    const existing = qc.getQueryData(["messages", tid]);
    if (existing) return;
    qc.setQueryData(["messages", tid], {
      pages: [data.messages as MessageListResponse],
      pageParams: [undefined],
    });
  }, [data, tid, qc]);

  if (isLoading)
    return (
      <AppShell>
        <SpinnerPage />
      </AppShell>
    );
  if (!data)
    return (
      <AppShell>
        <EmptyState icon="○" title="Ticket not found" />
      </AppShell>
    );

  const { ticket, thread_state } = data;

  return (
    <TicketView
      ticket={ticket}
      threadSummary={thread_state?.rolling_summary ?? null}
    />
  );
}

// ── TicketView ──
function TicketView({
  ticket,
  threadSummary,
}: {
  ticket: TicketRead;
  threadSummary: string | null;
}) {
  const { data: channel } = useChannel(ticket.channel_id);
  const { data: channelMembers } = useChannelMembers(ticket.channel_id);
  const { data: projectMembers } = useProjectMembers(channel?.project_id ?? "");
  const { data: channels } = useChannels(channel?.project_id ?? "");
  const user = useAuthStore((s) => s.user);

  const myProjectMember = projectMembers?.find((m) => m.user_id === user?.id);
  const isTeamLead = myProjectMember?.role === "team_lead";

  const myChannelMember = channelMembers?.find((m) => m.user_id === user?.id);
  const isChannelLead = myChannelMember?.role === "channel_lead";

  const isLocked =
    ["backlog", "routed", "split", "closed"].includes(ticket.status) &&
    !channel?.is_leads_channel;

  const activate = useActivateTicket(ticket.id, ticket.channel_id);
  const route = useRouteTicket(ticket.id);
  const split = useSplitTicket(ticket.id, ticket.channel_id);
  const generatePlan = useGeneratePlan(ticket.id, ticket.channel_id);

  const [showRoute, setShowRoute] = useState(false);
  const [selectedChannelId, setSelectedChannelId] = useState("");

  const [showSplit, setShowSplit] = useState(false);
  const [isSubmittingSplit, setIsSubmittingSplit] = useState(false);

  // Dynamic list of child tickets to create on the fly. Initializes with 2 blank drafts (as 2 is the minimum split count)
  const [childDrafts, setChildDrafts] = useState<ChildDraft[]>([
    { title: "", channelId: "", priority: ticket.priority },
    { title: "", channelId: "", priority: ticket.priority },
  ]);

  const disciplineChannels = channels?.filter((c) => !c.is_leads_channel) ?? [];

  // Pre-fill target channels once loaded
  useEffect(() => {
    if (
      showSplit &&
      disciplineChannels.length > 0 &&
      childDrafts[0].channelId === ""
    ) {
      const defaultChannel = disciplineChannels[0].id;
      setChildDrafts([
        { title: "", channelId: defaultChannel, priority: ticket.priority },
        { title: "", channelId: defaultChannel, priority: ticket.priority },
      ]);
    }
  }, [showSplit, disciplineChannels, ticket.priority]);

  const handleRouteSave = async () => {
    if (!selectedChannelId) return;
    await route.mutateAsync({ channel_id: selectedChannelId });
    setShowRoute(false);
  };

  const handleAddChildDraft = () => {
    setChildDrafts([
      ...childDrafts,
      {
        title: "",
        channelId: disciplineChannels[0]?.id ?? "",
        priority: ticket.priority,
      },
    ]);
  };

  const handleRemoveChildDraft = (index: number) => {
    if (childDrafts.length <= 2) return; // Keep minimum of 2
    setChildDrafts(childDrafts.filter((_, i) => i !== index));
  };

  const handleChildDraftChange = (
    index: number,
    field: keyof ChildDraft,
    value: string,
  ) => {
    setChildDrafts(
      childDrafts.map((draft, i) =>
        i === index ? { ...draft, [field]: value } : draft,
      ),
    );
  };

  // Orchestrated Split: Creates the child tickets dynamically first, then calls the split endpoint
  const handleSplitSave = async () => {
    if (childDrafts.some((d) => !d.title.trim())) {
      toast("Please provide a title for all child tickets", "error");
      return;
    }

    setIsSubmittingSplit(true);
    try {
      const createdIds: string[] = [];

      // 1. Create the child tickets in their target channels
      for (const draft of childDrafts) {
        const res = await ticketApi.create(draft.channelId, {
          title: draft.title.trim(),
          description: `Created during split of parent ticket: "${ticket.title}".`,
          priority: draft.priority,
        });
        createdIds.push(res.id);
      }

      // 2. Fire the split operation with the collected IDs
      await split.mutateAsync(createdIds);
      setShowSplit(false);
    } catch {
      toast("Failed to complete split operations", "error");
    } finally {
      setIsSubmittingSplit(false);
    }
  };

  return (
    <AppShell
      breadcrumbs={[
        { label: "Workspaces", href: "/" },
        ...(channel
          ? [
              { label: "Project", href: `/projects/${channel.project_id}` },
              { label: channel.name, href: `/channels/${ticket.channel_id}` },
            ]
          : []),
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
                  {/* Generate Plan Button */}
                  {["in_discussion", "consensus_reached"].includes(
                    ticket.status,
                  ) && (
                    <button
                      className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                      onClick={() => generatePlan.mutate()}
                      disabled={generatePlan.isPending}
                    >
                      {generatePlan.isPending ? "Triggering…" : "Generate plan"}
                    </button>
                  )}
                  {/* Route Button */}
                  {["backlog", "routed"].includes(ticket.status) &&
                    isTeamLead && (
                      <button
                        className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                        onClick={() => {
                          setSelectedChannelId(disciplineChannels[0]?.id ?? "");
                          setShowRoute(true);
                        }}
                      >
                        Route ticket
                      </button>
                    )}

                  {/* Split Button — Available for backlog, active, or in_discussion statuses */}
                  {["backlog", "active", "in_discussion"].includes(
                    ticket.status,
                  ) &&
                    isTeamLead && (
                      <button
                        className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                        onClick={() => {
                          setChildDrafts([
                            {
                              title: "",
                              channelId: disciplineChannels[0]?.id ?? "",
                              priority: ticket.priority,
                            },
                            {
                              title: "",
                              channelId: disciplineChannels[0]?.id ?? "",
                              priority: ticket.priority,
                            },
                          ]);
                          setShowSplit(true);
                        }}
                      >
                        Split ticket
                      </button>
                    )}

                  {/* Activate Button */}
                  {ticket.status === "routed" && isChannelLead && (
                    <button
                      className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                      onClick={() => activate.mutate()}
                      disabled={activate.isPending}
                    >
                      {activate.isPending ? "Activating…" : "Activate ticket"}
                    </button>
                  )}
                  <Link
                    to={`/channels/${ticket.channel_id}`}
                    className={styles.actionBtn}
                    style={{
                      textDecoration: "none",
                      display: "flex",
                      alignItems: "center",
                    }}
                  >
                    ← Back to channel
                  </Link>
                </div>
              </div>
            )}
          </aside>

          {/* Thread Panel */}
          <ThreadPanel
            ticketId={ticket.id}
            isLocked={isLocked}
            canReviewPlans={isTeamLead}
          />
        </div>
      </div>

      {/* Routing Destination Selection Modal */}
      {showRoute && (
        <Modal
          title="Route Ticket to Discipline Channel"
          onClose={() => setShowRoute(false)}
          footer={
            <>
              <Btn variant="ghost" onClick={() => setShowRoute(false)}>
                Cancel
              </Btn>
              <Btn
                variant="primary"
                onClick={handleRouteSave}
                loading={route.isPending}
              >
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

      {/* Orchestrated Split Modal */}
      {showSplit && (
        <Modal
          title="Split Ticket — Define Child Tickets"
          onClose={() => setShowSplit(false)}
          size="lg"
          footer={
            <>
              <Btn variant="ghost" onClick={() => setShowSplit(false)}>
                Cancel
              </Btn>
              <Btn
                variant="primary"
                onClick={handleSplitSave}
                loading={isSubmittingSplit}
              >
                Create & Split
              </Btn>
            </>
          }
        >
          <p
            style={{
              fontSize: 13,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              marginBottom: 16,
            }}
          >
            Define the child tickets to delegate your tasks. Clicking "Create &
            Split" will create these tickets inside their respective channels
            and close this parent ticket.
          </p>

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 16,
              maxHeight: 320,
              overflowY: "auto",
              paddingRight: 6,
            }}
          >
            {childDrafts.map((draft, idx) => (
              <div
                key={idx}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 1fr 1fr 40px",
                  gap: 10,
                  alignItems: "end",
                  paddingBottom: 16,
                  borderBottom: "1px solid var(--border-subtle)",
                }}
              >
                <TextField
                  label={`Child #${idx + 1} Title`}
                  value={draft.title}
                  onChange={(v) => handleChildDraftChange(idx, "title", v)}
                  placeholder="e.g. Implement backend authorization hooks"
                />

                <SelectField
                  label="Target Channel"
                  value={draft.channelId}
                  onChange={(v) => handleChildDraftChange(idx, "channelId", v)}
                  options={disciplineChannels.map((c) => ({
                    value: c.id,
                    label: c.name,
                  }))}
                />

                <SelectField
                  label="Priority"
                  value={draft.priority}
                  onChange={(v) => handleChildDraftChange(idx, "priority", v)}
                  options={[
                    { value: "low", label: "Low" },
                    { value: "medium", label: "Medium" },
                    { value: "high", label: "High" },
                    { value: "critical", label: "Critical" },
                  ]}
                />

                <button
                  type="button"
                  onClick={() => handleRemoveChildDraft(idx)}
                  disabled={childDrafts.length <= 2}
                  style={{
                    height: 38,
                    border: "1px solid var(--border-subtle)",
                    background: "transparent",
                    color: "var(--error)",
                    borderRadius: "var(--radius-md)",
                    cursor: childDrafts.length <= 2 ? "not-allowed" : "pointer",
                    opacity: childDrafts.length <= 2 ? 0.35 : 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                  title="Remove child ticket"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 14 }}>
            <Btn variant="ghost" onClick={handleAddChildDraft}>
              + Add another child ticket
            </Btn>
          </div>
        </Modal>
      )}
    </AppShell>
  );
}

// ── ThreadPanel ──
function ThreadPanel({
  ticketId,
  isLocked,
  canReviewPlans,
}: {
  ticketId: string;
  isLocked: boolean;
  canReviewPlans: boolean;
}) {
  const user = useAuthStore((s) => s.user);
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useMessages(ticketId);
  const send = useSendMessage(ticketId);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isFirstLoad = useRef(true);

  const allMessages: MessageRead[] = [];
  if (data) {
    const reversed = [...data.pages].reverse();
    for (const page of reversed) {
      allMessages.push(...page.items);
    }
  }

  useEffect(() => {
    if (isFirstLoad.current && allMessages.length > 0) {
      isFirstLoad.current = false;
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
  }, [allMessages.length]);

  useEffect(() => {
    if (isFirstLoad.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [allMessages.length]);

  const handleSend = useCallback(async () => {
    const content = draft.trim();
    if (!content || send.isPending || isLocked) return;
    setDraft("");
    await send.mutateAsync({ content });
    setTimeout(
      () => bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
      50,
    );
  }, [draft, send, isLocked]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaChange = (v: string) => {
    setDraft(v);
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  };

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
              {isFetchingNextPage ? "Loading…" : "Load earlier messages"}
            </button>
          </div>
        )}

        {allMessages.length === 0 && (
          <div style={{ margin: "auto", paddingTop: 40, textAlign: "center" }}>
            <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>
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
            canReviewPlans={canReviewPlans}
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
            placeholder={
              isLocked ? "This thread is locked..." : "Write a message…"
            }
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
          {isLocked ? "This thread is closed." : "⌘ + Enter to send"}
        </p>
      </div>
    </div>
  );
}

// ── MessageItem ──
function MessageItem({
  message,
  ticketId,
  isOwn,
  canReviewPlans,
}: {
  message: MessageRead;
  ticketId: string;
  isOwn: boolean;
  canReviewPlans: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState(message.content ?? "");
  const editMsg = useEditMessage(ticketId);
  const deleteMsg = useDeleteMessage(ticketId);

  if (message.type !== "human") {
    const planRunId = getPlanCardRunId(message);
    if (planRunId) {
      return (
        <PlanCard
          runId={planRunId}
          ticketId={ticketId}
          canReview={canReviewPlans}
        />
      );
    }
    return (
      <div className={styles.systemMessage}>
        <span className={styles.systemIcon}>⬡</span>
        <span>{message.content ?? "Agent event"}</span>
      </div>
    );
  }

  const authorInitial = message.author?.display_name?.[0]?.toUpperCase() ?? "?";

  const handleSaveEdit = async () => {
    if (!editDraft.trim()) return;
    await editMsg.mutateAsync({
      messageId: message.id,
      data: { content: editDraft.trim() },
    });
    setEditing(false);
  };

  const handleDelete = () => {
    deleteMsg.mutate(message.id);
  };

  return (
    <div className={styles.messageGroup}>
      {message.author?.avatar_url ? (
        <img
          src={message.author.avatar_url}
          alt=""
          className={styles.avatarImg}
        />
      ) : (
        <div className={styles.avatar}>{authorInitial}</div>
      )}

      <div className={styles.messageBody}>
        <div className={styles.messageHeader}>
          <span className={styles.authorName}>
            {message.author?.display_name ?? "Unknown"}
          </span>
          <span className={styles.messageTime}>
            {timeAgo(message.created_at)}
          </span>
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
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter")
                  handleSaveEdit();
                if (e.key === "Escape") setEditing(false);
              }}
              autoFocus
            />
            <div className={styles.editActions}>
              <Btn
                size="sm"
                variant="primary"
                onClick={handleSaveEdit}
                loading={editMsg.isPending}
              >
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
              onClick={() => {
                setEditDraft(message.content ?? "");
                setEditing(true);
              }}
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
  );
}

function SendIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 2L2 6.5l5 2 2 5L14 2z" />
    </svg>
  );
}
