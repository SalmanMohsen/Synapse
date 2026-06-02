import { AppShell, shellStyles as s } from "@/shared/components/AppShell";
import { SpinnerPage, EmptyState, Badge, Btn } from "@/shared/components";
import {
  useInbox,
  useAcceptInvite,
  useDeclineInvite,
  useMarkRead,
} from "../hooks/useInbox";
import type { InboxItem } from "../types/inbox.types";
import { useState } from "react";

type Tab = "invites" | "notifications" | "all";

export default function InboxPage() {
  const { data: items, isLoading } = useInbox();
  const [tab, setTab] = useState<Tab>("invites");

  const invites =
    items?.filter(
      (i) => i.type.endsWith("_invite") && i.status === "pending",
    ) ?? [];
  const notifications = items?.filter((i) => i.type === "notification") ?? [];
  const all = items ?? [];

  const displayed =
    tab === "invites" ? invites : tab === "notifications" ? notifications : all;

  return (
    <AppShell breadcrumbs={[{ label: "Inbox" }]}>
      <div className={s.sectionHead}>
        <h1 className={s.pageTitle}>Inbox</h1>
      </div>

      <div className={s.tabs}>
        <button
          className={`${s.tab} ${tab === "invites" ? s.tabActive : ""}`}
          onClick={() => setTab("invites")}
        >
          Invites {invites.length > 0 && `(${invites.length})`}
        </button>
        <button
          className={`${s.tab} ${tab === "notifications" ? s.tabActive : ""}`}
          onClick={() => setTab("notifications")}
        >
          Notifications
        </button>
        <button
          className={`${s.tab} ${tab === "all" ? s.tabActive : ""}`}
          onClick={() => setTab("all")}
        >
          All
        </button>
      </div>

      {isLoading ? (
        <SpinnerPage />
      ) : displayed.length === 0 ? (
        <EmptyState
          icon="◉"
          title={
            tab === "invites"
              ? "No pending invites"
              : tab === "notifications"
                ? "No notifications"
                : "Inbox is empty"
          }
          body="You're all caught up."
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {displayed.map((item) =>
            item.type.endsWith("_invite") ? (
              <InviteItem key={item.id} item={item} />
            ) : (
              <NotificationItem key={item.id} item={item} />
            ),
          )}
        </div>
      )}
    </AppShell>
  );
}

function InviteItem({ item }: { item: InboxItem }) {
  const accept = useAcceptInvite();
  const decline = useDeclineInvite();

  const scope = item.channel_id
    ? "channel"
    : item.project_id
      ? "project"
      : "workspace";

  const expiryMs = item.expires_at
    ? new Date(item.expires_at).getTime() - Date.now()
    : null;
  const soonExpiry = expiryMs !== null && expiryMs < 48 * 3600 * 1000;

  const isPending = item.status === "pending";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "14px 16px",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        background: "var(--bg-surface)",
        animation: "fadeUp 0.2s var(--ease) both",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            marginBottom: 4,
          }}
        >
          <span
            style={{
              fontSize: 13,
              fontWeight: 500,
              color: "var(--text-primary)",
            }}
          >
            {item.title}
          </span>
          <Badge variant="default">{scope}</Badge>
          {item.role && <Badge variant="brand">{item.role}</Badge>}
          {soonExpiry && <Badge variant="warning">Expiring soon</Badge>}
        </div>
        {item.body && (
          <p
            style={{
              fontSize: 12,
              color: "var(--text-tertiary)",
              lineHeight: 1.5,
            }}
          >
            {item.body}
          </p>
        )}
        <p
          style={{
            fontSize: 11,
            color: "var(--text-tertiary)",
            marginTop: 4,
            fontFamily: "var(--font-mono)",
          }}
        >
          {new Date(item.created_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </p>
      </div>

      {isPending ? (
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <Btn
            size="sm"
            variant="primary"
            onClick={() => accept.mutate(item.id)}
            loading={accept.isPending}
          >
            Accept
          </Btn>
          <Btn
            size="sm"
            variant="ghost"
            onClick={() => decline.mutate(item.id)}
            loading={decline.isPending}
          >
            Decline
          </Btn>
        </div>
      ) : (
        <Badge variant={item.status === "accepted" ? "success" : "default"}>
          {item.status}
        </Badge>
      )}
    </div>
  );
}

function NotificationItem({ item }: { item: InboxItem }) {
  const markRead = useMarkRead();
  const isUnread = item.status === "unread";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        padding: "12px 16px",
        border: `1px solid ${isUnread ? "var(--border-default)" : "var(--border-subtle)"}`,
        borderRadius: "var(--radius-lg)",
        background: isUnread ? "var(--bg-elevated)" : "var(--bg-surface)",
        cursor: isUnread ? "pointer" : "default",
        transition: "background 0.12s",
        animation: "fadeUp 0.2s var(--ease) both",
      }}
      onClick={() => {
        if (isUnread) markRead.mutate(item.id);
      }}
    >
      {isUnread && (
        <span
          style={{
            marginTop: 5,
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: "var(--brand)",
            flexShrink: 0,
          }}
        />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontSize: 13,
            fontWeight: isUnread ? 500 : 400,
            color: "var(--text-primary)",
            marginBottom: 2,
          }}
        >
          {item.title}
        </p>
        {item.body && (
          <p
            style={{
              fontSize: 12,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
            }}
          >
            {item.body}
          </p>
        )}
        <p
          style={{
            fontSize: 11,
            color: "var(--text-tertiary)",
            marginTop: 4,
            fontFamily: "var(--font-mono)",
          }}
        >
          {new Date(item.created_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
          })}
          {isUnread && " · click to mark as read"}
        </p>
      </div>
    </div>
  );
}
