import { useState, useRef, useEffect, type ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useLogout } from '@/features/auth/hooks/useAuth'
import { useUnreadCount } from '@/features/inbox/hooks/useInbox'
import styles from './AppShell.module.css'

// ── Top nav ───────────────────────────────────────────────────────────────────

interface BreadcrumbItem {
  label: string
  href?: string
}

export function AppShell({
  children,
  breadcrumbs,
  wide,
}: {
  children: ReactNode
  breadcrumbs?: BreadcrumbItem[]
  wide?: boolean
}) {
  return (
    <div className={styles.page}>
      <TopBar breadcrumbs={breadcrumbs} />
      <div className={wide ? styles.pageContentWide : styles.pageContent}>
        {children}
      </div>
    </div>
  )
}

function TopBar({ breadcrumbs }: { breadcrumbs?: BreadcrumbItem[] }) {
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()
  const navigate = useNavigate()
  const unread = useUnreadCount()
  const [dropOpen, setDropOpen] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!dropRef.current?.contains(e.target as Node)) setDropOpen(false)
    }
    if (dropOpen) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [dropOpen])

  return (
    <header className={styles.topbar}>
      <Link to="/" className={styles.logo}>
        <span className={styles.logoMark}>
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
            <circle cx="4" cy="7" r="2" fill="#6366f1" />
            <circle cx="10" cy="7" r="2" fill="#6366f1" opacity="0.4" />
            <path d="M6 7 Q7 4.5 8 7" stroke="#6366f1" strokeWidth="1.2" fill="none" strokeLinecap="round" />
          </svg>
        </span>
        Synapse
      </Link>

      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className={styles.breadcrumb} aria-label="Breadcrumb">
          {breadcrumbs.map((crumb, i) => {
            const isLast = i === breadcrumbs.length - 1
            return (
              <span key={i} style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
                {i > 0 && <span className={styles.breadcrumbSep}>/</span>}
                {crumb.href && !isLast ? (
                  <Link to={crumb.href} className={styles.breadcrumbItem}>{crumb.label}</Link>
                ) : (
                  <span className={`${styles.breadcrumbItem} ${isLast ? styles.breadcrumbCurrent : ''}`}>
                    {crumb.label}
                  </span>
                )}
              </span>
            )
          })}
        </nav>
      )}

      <div className={styles.right}>
        <NavLink
          to="/inbox"
          className={({ isActive }) =>
            `${styles.inboxBtn} ${isActive ? styles.inboxBtnActive : ''}`
          }
          aria-label="Inbox"
        >
          <InboxIcon />
          {unread > 0 && (
            <span className={styles.badge}>{unread > 9 ? '9+' : unread}</span>
          )}
        </NavLink>

        <div className={styles.userMenu} ref={dropRef}>
          <button className={styles.userBtn} onClick={() => setDropOpen((v) => !v)}>
            <div className={styles.userAvatar}>
              {user?.display_name?.[0]?.toUpperCase() ?? '?'}
            </div>
            <span className={styles.userName}>{user?.display_name}</span>
          </button>
          {dropOpen && (
            <div className={styles.dropdown}>
              <Link
                to="/settings"
                className={styles.dropdownItem}
                onClick={() => setDropOpen(false)}
              >
                Settings
              </Link>
              <div className={styles.dropdownDivider} />
              <button
                className={`${styles.dropdownItem} ${styles.dropdownDanger}`}
                onClick={() => { setDropOpen(false); logout.mutate() }}
                disabled={logout.isPending}
              >
                {logout.isPending ? 'Signing out…' : 'Sign out'}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

function InboxIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 4h12v9H2z" />
      <path d="M2 4l6 5 6-5" />
    </svg>
  )
}

// Re-export shell helpers
export { styles as shellStyles }