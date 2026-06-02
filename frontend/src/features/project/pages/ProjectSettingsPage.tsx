import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { AppShell, shellStyles as s } from "@/shared/components/AppShell";
import { SpinnerPage, EmptyState, Btn, TextField, ConfirmDialog } from "@/shared/components";
import { useAuthStore } from "@/features/auth/store/authSlice";
import { useProject, useUpdateProject, useDeleteProject, useProjectMembers } from "../hooks/useProjects";
import { useWorkspaceMembers } from "@/features/workspace/hooks/useWorkspaces";

type Section = "general" | "danger";

export default function ProjectSettingsPage() {
  const { pid } = useParams<{ pid: string }>();
  const { data: project, isLoading: projLoading } = useProject(pid!);
  const { data: members, isLoading: memLoading } = useProjectMembers(pid!);
  const { data: workspaceMembers, isLoading: wsLoading } = useWorkspaceMembers(project?.workspace_id ?? "");
  const user = useAuthStore((s) => s.user);
  const [active, setActive] = useState<Section>("general");

  const isLoading = projLoading || memLoading || wsLoading;

  if (isLoading) return <AppShell><SpinnerPage /></AppShell>;
  if (!project) return <AppShell><EmptyState icon="○" title="Project not found" /></AppShell>;

  const myMember = members?.find((m) => m.user_id === user?.id);
  const isLead = myMember?.role === "team_lead";
  const myWsMember = workspaceMembers?.find((m) => m.user_id === user?.id);
  const isWorkspaceOwner = myWsMember?.is_owner ?? false;

  if (!isLead && !isWorkspaceOwner) {
    return (
      <AppShell>
        <EmptyState icon="⊘" title="Access denied" body="Only project leads or workspace owners can access project settings." />
      </AppShell>
    );
  }

  const NAV: { id: Section; label: string }[] = [
    { id: "general", label: "General" },
    ...(isWorkspaceOwner ? [{ id: "danger" as Section, label: "Danger zone" }] : []),
  ];

  return (
    <AppShell
      breadcrumbs={[
        { label: "Workspaces", href: "/" },
        { label: project.name, href: `/projects/${pid}` },
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
          {active === "general" && <GeneralSection project={project} />}
          {active === "danger" && isWorkspaceOwner && <DangerSection project={project} />}
        </div>
      </div>
    </AppShell>
  );
}

function GeneralSection({ project }: { project: any }) {
  const update = useUpdateProject(project.id);
  const [name, setName] = useState(project.name);
  const [branch, setBranch] = useState(project.default_branch);
  const [nameErr, setNameErr] = useState("");

  const handleSave = async () => {
    if (!name.trim() || name.trim().length < 2) {
      setNameErr("At least 2 characters");
      return;
    }
    await update.mutateAsync({ name: name.trim(), default_branch: branch.trim() || "main" });
  };

  return (
    <div className={s.settingsSection}>
      <p className={s.settingsSectionTitle}>General Settings</p>
      <TextField
        label="Project name"
        value={name}
        onChange={(v) => { setName(v); setNameErr(""); }}
        error={nameErr}
      />
      <TextField
        label="Default branch"
        value={branch}
        onChange={setBranch}
      />
      <div style={{ marginTop: 8 }}>
        <Btn variant="primary" onClick={handleSave} loading={update.isPending}>
          Save changes
        </Btn>
      </div>
    </div>
  );
}

function DangerSection({ project }: { project: any }) {
  const navigate = useNavigate();
  const deleteProj = useDeleteProject();
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <div className={s.settingsSection}>
      <p className={s.settingsSectionTitle}>Danger zone</p>
      <div className={s.dangerZone}>
        <div className={s.dangerRow}>
          <div className={s.dangerText}>
            <p>Delete project</p>
            <p>Permanently deletes this project and all its channels. This action cannot be undone.</p>
          </div>
          <Btn variant="danger" onClick={() => setConfirmOpen(true)}>
            Delete
          </Btn>
        </div>
      </div>
      {confirmOpen && (
        <ConfirmDialog
          title="Delete project?"
          body={`This will permanently delete the project "${project.name}". This cannot be undone.`}
          confirmLabel="Delete project"
          danger
          loading={deleteProj.isPending}
          onConfirm={async () => {
            await deleteProj.mutateAsync({ id: project.id, workspaceId: project.workspace_id });
            navigate(`/workspaces/${project.workspace_id}`);
          }}
          onClose={() => setConfirmOpen(false)}
        />
      )}
    </div>
  );
}