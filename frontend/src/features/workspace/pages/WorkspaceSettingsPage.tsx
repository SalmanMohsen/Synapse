import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { AppShell, shellStyles as s } from "@/shared/components/AppShell";
import {
  SpinnerPage,
  EmptyState,
  Badge,
  MemberRow,
  Modal,
  TextField,
  SelectField,
  ToggleField,
  Btn,
  ConfirmDialog,
} from "@/shared/components";
import { useAuthStore } from "@/features/auth/store/authSlice";
import {
  useWorkspace,
  useWorkspaceMembers,
  useUpdateWorkspace,
  useDeleteWorkspace,
  usePromoteToOwner,
  useRemoveWorkspaceMember,
} from "../hooks/useWorkspaces";
import { useSendWorkspaceInvite } from "@/features/inbox/hooks/useInbox";
import type { User } from "@/features/auth/types/auth.types";
import { UserSearchField } from "@/shared/components";
import { authApi } from "@/features/auth/api/authApi";

type Section = "general" | "members" | "danger";

export default function WorkspaceSettingsPage() {
  const { wid } = useParams<{ wid: string }>();
  const { data: workspace, isLoading } = useWorkspace(wid!);
  const { data: members } = useWorkspaceMembers(wid!);
  const user = useAuthStore((s) => s.user);
  const [active, setActive] = useState<Section>("general");

  const myMembership = members?.find((m) => m.user_id === user?.id);
  if (!myMembership?.is_owner && !isLoading) {
    return (
      <AppShell>
        <EmptyState
          icon="⊘"
          title="Access denied"
          body="Only owners can access workspace settings."
        />
      </AppShell>
    );
  }

  if (isLoading)
    return (
      <AppShell>
        <SpinnerPage />
      </AppShell>
    );
  if (!workspace)
    return (
      <AppShell>
        <EmptyState icon="○" title="Workspace not found" />
      </AppShell>
    );

  const NAV: { id: Section; label: string }[] = [
    { id: "general", label: "General" },
    { id: "members", label: "Members" },
    { id: "danger", label: "Danger zone" },
  ];

  return (
    <AppShell
      breadcrumbs={[
        { label: "Workspaces", href: "/" },
        { label: workspace.name, href: `/workspaces/${wid}` },
        { label: "Settings" },
      ]}
    >
      <div className={s.settingsLayout}>
        <nav className={s.settingsSidebar}>
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`${s.settingsNav} ${active === n.id ? s.settingsNavActive : ""}`}
              onClick={() => setActive(n.id)}
            >
              {n.label}
            </button>
          ))}
        </nav>

        <div className={s.settingsContent}>
          {active === "general" && <GeneralSection workspaceId={wid!} />}
          {active === "members" && <MembersSection workspaceId={wid!} />}
          {active === "danger" && <DangerSection workspaceId={wid!} />}
        </div>
      </div>
    </AppShell>
  );
}

function GeneralSection({ workspaceId }: { workspaceId: string }) {
  const { data: workspace } = useWorkspace(workspaceId);
  const update = useUpdateWorkspace(workspaceId);
  const [name, setName] = useState(workspace?.name ?? "");
  const [openPolicy, setOpenPolicy] = useState(
    workspace?.project_creation_policy === "open",
  );
  const [nameErr, setNameErr] = useState("");

  if (!workspace) return null;

  const handleSaveName = async () => {
    if (!name.trim() || name.trim().length < 2) {
      setNameErr("At least 2 characters");
      return;
    }
    await update.mutateAsync({ name: name.trim() });
    setNameErr("");
  };

  const handleTogglePolicy = async (v: boolean) => {
    setOpenPolicy(v);
    await update.mutateAsync({
      project_creation_policy: v ? "open" : "restricted",
    });
  };

  return (
    <div className={s.settingsSection}>
      <p className={s.settingsSectionTitle}>General</p>
      <div className={s.inlineForm}>
        <TextField
          label="Workspace name"
          value={name}
          onChange={(v) => {
            setName(v);
            setNameErr("");
          }}
          placeholder="Acme Corp"
          error={nameErr}
        />
        <Btn
          variant="ghost"
          onClick={handleSaveName}
          loading={update.isPending}
        >
          Save
        </Btn>
      </div>
      <ToggleField
        label="Open project creation"
        description="Allow any member to create projects"
        checked={openPolicy}
        onChange={handleTogglePolicy}
      />
    </div>
  );
}

function MembersSection({ workspaceId }: { workspaceId: string }) {
  const { data: members, isLoading } = useWorkspaceMembers(workspaceId);
  const promote = usePromoteToOwner(workspaceId);
  const remove = useRemoveWorkspaceMember(workspaceId);
  const sendInvite = useSendWorkspaceInvite(workspaceId);
  const user = useAuthStore((s) => s.user);
  const myMember = members?.find((m) => m.user_id === user?.id);
  const [showInvite, setShowInvite] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  if (isLoading) return <SpinnerPage />;

  return (
    <div className={s.settingsSection}>
      <p className={s.settingsSectionTitle}>Members</p>
      <div className={s.listPanel}>
        <div className={s.listPanelHeader}>
          <span className={s.listPanelTitle}>
            {members?.length ?? 0} members
          </span>
          <Btn size="sm" variant="ghost" onClick={() => setShowInvite(true)}>
            Invite member
          </Btn>
        </div>
        <div className={s.listPanelBody}>
          {members?.map((m) => {
            const isMe = m.user_id === user?.id;
            const canAct = !isMe && myMember?.is_owner;
            return (
              <MemberRow
                key={m.id}
                name={m.user?.display_name ?? m.user_id}
                subtitle={m.user?.email}
                badges={
                  <Badge variant={m.is_owner ? "brand" : "default"}>
                    {m.is_owner ? "Owner" : "Member"}
                  </Badge>
                }
                actions={
                  canAct ? (
                    <>
                      {!m.is_owner && (
                        <Btn
                          size="sm"
                          variant="ghost"
                          onClick={() => promote.mutate(m.user_id)}
                          loading={promote.isPending}
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
            );
          })}
        </div>
      </div>

      {showInvite && (
        <InviteModal
          title="Invite to workspace"
          roles={[
            { value: "member", label: "Member" },
            { value: "owner", label: "Owner" },
          ]}
          onInvite={(userId, role) =>
            sendInvite
              .mutateAsync({ target_user_id: userId, role })
              .then(() => setShowInvite(false))
          }
          onClose={() => setShowInvite(false)}
          loading={sendInvite.isPending}
          scopeKey="platform" // <-- Pass scope
          searchFn={(q) => authApi.searchUsers(q)} // <-- Pass platform search
        />
      )}

      {removeTarget && (
        <ConfirmDialog
          title="Remove member"
          body="This will remove the member from the workspace."
          confirmLabel="Remove"
          danger
          onConfirm={() => {
            remove.mutate(removeTarget);
            setRemoveTarget(null);
          }}
          onClose={() => setRemoveTarget(null)}
          loading={remove.isPending}
        />
      )}
    </div>
  );
}

function DangerSection({ workspaceId }: { workspaceId: string }) {
  const navigate = useNavigate();
  const deleteWs = useDeleteWorkspace();
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <div className={s.settingsSection}>
      <p className={s.settingsSectionTitle}>Danger zone</p>
      <div className={s.dangerZone}>
        <div className={s.dangerRow}>
          <div className={s.dangerText}>
            <p>Delete workspace</p>
            <p>
              Permanently deletes this workspace and all its projects. Cannot be
              undone.
            </p>
          </div>
          <Btn variant="danger" onClick={() => setConfirmOpen(true)}>
            Delete
          </Btn>
        </div>
      </div>
      {confirmOpen && (
        <ConfirmDialog
          title="Delete workspace?"
          body="This will permanently delete the workspace and all associated projects. This cannot be undone."
          confirmLabel="Delete workspace"
          danger
          loading={deleteWs.isPending}
          onConfirm={async () => {
            await deleteWs.mutateAsync(workspaceId);
            navigate("/");
          }}
          onClose={() => setConfirmOpen(false)}
        />
      )}
    </div>
  );
}

// Shared invite modal used in workspace + project + channel settings
export function InviteModal({
  title,
  roles,
  onInvite,
  onClose,
  loading,
  scopeKey, // <-- Add this
  searchFn, // <-- Add this
}: {
  title: string;
  roles: { value: string; label: string }[];
  onInvite: (userId: string, role: string) => Promise<void>;
  onClose: () => void;
  loading: boolean;
  scopeKey: string; // <-- Add this
  searchFn: (q: string) => Promise<User[]>; // <-- Add this
}) {
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [role, setRole] = useState(roles[0]?.value ?? "member");
  const [err, setErr] = useState("");

  const handleSend = async () => {
    if (!selectedUser) {
      setErr("Please select a user to invite");
      return;
    }
    await onInvite(selectedUser.id, role);
  };

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            Cancel
          </Btn>
          <Btn variant="primary" onClick={handleSend} loading={loading}>
            Send invite
          </Btn>
        </>
      }
    >
      <UserSearchField
        label="User"
        selectedUser={selectedUser}
        onSelect={(user) => {
          setSelectedUser(user);
          setErr("");
        }}
        scopeKey={scopeKey} // <-- Use the prop
        searchFn={searchFn} // <-- Use the prop
        error={err}
      />
      <SelectField
        label="Role"
        value={role}
        onChange={setRole}
        options={roles}
      />
    </Modal>
  );
}
