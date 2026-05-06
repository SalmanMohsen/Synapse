import { useState } from 'react'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useLogout } from '@/features/auth/hooks/useAuth'
import ConnectedAccounts from '@/features/auth/components/ConnectedAccounts'
import styles from './SettingsPage.module.css'

type Section = 'profile' | 'accounts' | 'danger'

const NAV: { id: Section; label: string }[] = [
  { id: 'profile',  label: 'Profile'            },
  { id: 'accounts', label: 'Connected accounts' },
  { id: 'danger',   label: 'Danger zone'        },
]

export default function SettingsPage() {
  const [active, setActive] = useState<Section>('profile')

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <a href="/" className={styles.back}>
          <ChevronLeft />
          Back
        </a>
        <span className={styles.topbarTitle}>Settings</span>
      </header>

      <div className={styles.layout}>
        {/* ── Sidebar nav ── */}
        <nav className={styles.sidebar}>
          {NAV.map((item) => (
            <button
              key={item.id}
              className={`${styles.navItem} ${active === item.id ? styles.navItemActive : ''}`}
              onClick={() => setActive(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {/* ── Content ── */}
        <main className={styles.content}>
          {active === 'profile'  && <ProfileSection />}
          {active === 'accounts' && <AccountsSection />}
          {active === 'danger'   && <DangerSection />}
        </main>
      </div>
    </div>
  )
}

// ── Profile section ───────────────────────────────────────────────────────────

function ProfileSection() {
  const user = useAuthStore((s) => s.user)
  if (!user) return null

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Profile"
        description="Your public identity on Synapse."
      />

      <div className={styles.profileCard}>
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className={styles.profileAvatar} />
        ) : (
          <div className={styles.profileAvatarFallback}>
            {user.display_name?.[0]?.toUpperCase() ?? '?'}
          </div>
        )}
        <div className={styles.profileMeta}>
          <span className={styles.profileName}>{user.display_name}</span>
          <span className={styles.profileEmail}>{user.email}</span>
          <span className={styles.profileJoined}>
            Member since {new Date(user.created_at).toLocaleDateString('en-US', {
              month: 'long', year: 'numeric',
            })}
          </span>
        </div>
      </div>

      <Field label="Display name">
        <ReadOnlyInput value={user.display_name} />
      </Field>

      <Field label="Email address">
        <ReadOnlyInput value={user.email} />
      </Field>

      <p className={styles.fieldHint}>
        Profile editing will be available in a future update.
      </p>
    </div>
  )
}

// ── Connected accounts section ────────────────────────────────────────────────

function AccountsSection() {
  return (
    <div className={styles.section}>
      <SectionHeader
        title="Connected accounts"
        description="Link additional sign-in methods. Once linked, you can use any of them to sign in."
      />
      <ConnectedAccounts />
    </div>
  )
}

// ── Danger zone section ───────────────────────────────────────────────────────

function DangerSection() {
  const logout = useLogout()
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Danger zone"
        description="Destructive actions that cannot be undone."
      />

      <div className={styles.dangerCard}>
        <div>
          <p className={styles.dangerTitle}>Sign out of all sessions</p>
          <p className={styles.dangerBody}>
            Revokes all active tokens. You will be signed out immediately.
          </p>
        </div>
        <button
          className={styles.btnDanger}
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          {logout.isPending ? 'Signing out…' : 'Sign out'}
        </button>
      </div>

      <div className={styles.dangerCard}>
        <div>
          <p className={styles.dangerTitle}>Delete account</p>
          <p className={styles.dangerBody}>
            Permanently deletes your account and all associated data.
            This cannot be undone.
          </p>
        </div>
        <button
          className={styles.btnDanger}
          onClick={() => setConfirmOpen(true)}
          disabled
          title="Coming in a future update"
        >
          Delete account
        </button>
      </div>

      {confirmOpen && (
        <DeleteConfirmDialog onClose={() => setConfirmOpen(false)} />
      )}
    </div>
  )
}

// ── Delete confirm dialog ─────────────────────────────────────────────────────

function DeleteConfirmDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.dialogBackdrop} onClick={onClose}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <p className={styles.dialogTitle}>Delete account?</p>
        <p className={styles.dialogBody}>
          This will permanently delete your account and cannot be undone.
        </p>
        <div className={styles.dialogActions}>
          <button className={styles.btnGhost} onClick={onClose}>Cancel</button>
          <button className={styles.btnDanger} disabled>Delete</button>
        </div>
      </div>
    </div>
  )
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className={styles.sectionHeader}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      <p className={styles.sectionDescription}>{description}</p>
      <div className={styles.sectionDivider} />
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel}>{label}</label>
      {children}
    </div>
  )
}

function ReadOnlyInput({ value }: { value: string }) {
  return (
    <div className={styles.readOnlyInput}>
      {value}
    </div>
  )
}

function ChevronLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M10.5 3L5.5 8l5 5" stroke="currentColor" strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}