import { type ReactNode, useEffect, useState } from 'react'
import styles from './shared.module.css'
import type { ToastVariant } from '../hooks/useToast'
import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { authApi } from '@/features/auth/api/authApi'
import type { User } from '@/features/auth/types/auth.types'

// ── Spinner ──────────────────────────────────────────────────────────────────

export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span
      className={`${styles.spinner} ${size === 'sm' ? styles.spinnerSm : ''} ${size === 'lg' ? styles.spinnerLg : ''}`}
      aria-label="Loading"
    />
  )
}

export function SpinnerPage() {
  return (
    <div className={styles.spinnerPage}>
      <Spinner size="lg" />
    </div>
  )
}

// ── Badge ────────────────────────────────────────────────────────────────────

type BadgeVariant = 'default' | 'brand' | 'success' | 'error' | 'warning'
  | 'frontend' | 'backend' | 'database' | 'devops' | 'ai_ml'

const BADGE_VARIANT_MAP: Record<BadgeVariant, string> = {
  default:  styles.badgeDefault,
  brand:    styles.badgeBrand,
  success:  styles.badgeSuccess,
  error:    styles.badgeError,
  warning:  styles.badgeWarning,
  frontend: styles.badgeFrontend,
  backend:  styles.badgeBackend,
  database: styles.badgeDatabase,
  devops:   styles.badgeDevops,
  ai_ml:    styles.badgeAiml,
}

export function Badge({ children, variant = 'default' }: { children: ReactNode; variant?: BadgeVariant }) {
  return (
    <span className={`${styles.badge} ${BADGE_VARIANT_MAP[variant]}`}>
      {children}
    </span>
  )
}

// Map discipline string → badge variant
export function DisciplineBadge({ discipline }: { discipline: string | null }) {
  if (!discipline) return null
  const label = DISCIPLINE_LABELS[discipline] ?? discipline
  const variant = (DISCIPLINE_BADGE_VARIANTS[discipline] ?? 'default') as BadgeVariant
  return <Badge variant={variant}>{label}</Badge>
}

export const DISCIPLINE_LABELS: Record<string, string> = {
  frontend: 'Frontend',
  backend:  'Backend',
  database: 'Database',
  devops:   'DevOps',
  ai_ml:    'AI / ML',
}

const DISCIPLINE_BADGE_VARIANTS: Record<string, string> = {
  frontend: 'frontend',
  backend:  'backend',
  database: 'database',
  devops:   'devops',
  ai_ml:    'ai_ml',
}

// ── EmptyState ────────────────────────────────────────────────────────────────

export function EmptyState({
  icon = '○',
  title,
  body,
  action,
}: {
  icon?: string
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <div className={styles.emptyState}>
      <span className={styles.emptyIcon}>{icon}</span>
      <p className={styles.emptyTitle}>{title}</p>
      {body && <p className={styles.emptyBody}>{body}</p>}
      {action}
    </div>
  )
}

// ── Modal ────────────────────────────────────────────────────────────────────

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  size?: 'md' | 'lg'
}

export function Modal({ title, onClose, children, footer, size = 'md' }: ModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={`${styles.modal} ${size === 'lg' ? styles.modalLg : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalHeader}>
          <p className={styles.modalTitle}>{title}</p>
          <button className={styles.modalClose} onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </div>
        <div className={styles.modalBody}>{children}</div>
        {footer && <div className={styles.modalFooter}>{footer}</div>}
      </div>
    </div>
  )
}

// ── ConfirmDialog ─────────────────────────────────────────────────────────────

export function ConfirmDialog({
  title,
  body,
  confirmLabel = 'Confirm',
  danger = false,
  onConfirm,
  onClose,
  loading = false,
}: {
  title: string
  body: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onClose: () => void
  loading?: boolean
}) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button className={`${styles.btn} ${styles.btnGhost}`} onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className={`${styles.btn} ${danger ? styles.btnDanger : styles.btnPrimary}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? 'Please wait…' : confirmLabel}
          </button>
        </>
      }
    >
      <p className={styles.confirmBody}>{body}</p>
    </Modal>
  )
}

// ── Toast container ───────────────────────────────────────────────────────────

interface ToastItem {
  id: string
  message: string
  variant: ToastVariant
}

export function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}) {
  if (!toasts.length) return null
  return (
    <div className={styles.toastContainer} aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`${styles.toast} ${t.variant === 'success' ? styles.toastSuccess : ''} ${t.variant === 'error' ? styles.toastError : ''}`}
        >
          {t.message}
          <button className={styles.toastDismiss} onClick={() => onDismiss(t.id)} aria-label="Dismiss">×</button>
        </div>
      ))}
    </div>
  )
}

export function UserSearchField({
  label,
  selectedUser,
  onSelect,
  searchFn,      
  scopeKey,
  error
}: {
  label: string
  selectedUser: User | null
  onSelect: (user: User | null) => void
  searchFn: (query: string) => Promise<User[]>
  scopeKey: string
  error?: string
}) {
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const { data: users, isLoading } = useQuery({
    queryKey: ['users', 'search', scopeKey, query],
    queryFn: () => searchFn(query),
    enabled: query.length >= 2,
  })

  // Close the dropdown when clicking outside of it
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className={styles.field} ref={wrapperRef}>
      <label className={styles.label}>{label}</label>
      <div className={styles.autocompleteWrap}>
        <input
          className={`${styles.input} ${error ? styles.fieldError : ''}`}
          value={selectedUser ? selectedUser.display_name : query}
          onChange={(e) => {
            setQuery(e.target.value)
            onSelect(null) // Clear selection if they start typing again
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="Search by name or email…"
          autoComplete="off"
        />
        
        {isOpen && query.length >= 2 && (
          <div className={styles.autocompleteList}>
            {isLoading ? (
              <div className={styles.autocompleteEmpty}>Searching...</div>
            ) : !users || users.length === 0 ? (
              <div className={styles.autocompleteEmpty}>No users found</div>
            ) : (
              users.map((u) => (
                <div
                  key={u.id}
                  className={styles.autocompleteItem}
                  onClick={() => {
                    onSelect(u)
                    setQuery('')
                    setIsOpen(false)
                  }}
                >
                  <span className={styles.autocompleteName}>{u.display_name}</span>
                  <span className={styles.autocompleteEmail}>{u.email}</span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
      {error && <span className={styles.errorMsg}>{error}</span>}
    </div>
  )
}

// ── Form helpers ──────────────────────────────────────────────────────────────

export function Field({ label, children, error }: { label: string; children: ReactNode; error?: string }) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      {children}
      {error && <span className={styles.errorMsg}>{error}</span>}
    </div>
  )
}

interface TextFieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  error?: string
  autoFocus?: boolean
}

export function TextField({ label, value, onChange, placeholder, error, autoFocus }: TextFieldProps) {
  return (
    <Field label={label} error={error}>
      <input
        className={`${styles.input} ${error ? styles.fieldError : ''}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
      />
    </Field>
  )
}

interface SelectFieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  error?: string
}

export function SelectField({ label, value, onChange, options, error }: SelectFieldProps) {
  return (
    <Field label={label} error={error}>
      <select
        className={`${styles.select} ${error ? styles.fieldError : ''}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </Field>
  )
}

interface ToggleFieldProps {
  label: string
  description?: string
  checked: boolean
  onChange: (v: boolean) => void
}

export function ToggleField({ label, description, checked, onChange }: ToggleFieldProps) {
  return (
    <label className={styles.toggle}>
      <div
        className={`${styles.toggleTrack} ${checked ? styles.toggleTrackOn : ''}`}
        onClick={() => onChange(!checked)}
      >
        <div className={`${styles.toggleThumb} ${checked ? styles.toggleThumbOn : ''}`} />
      </div>
      <span className={styles.toggleLabel}>
        {label}{description && <span style={{ color: 'var(--text-tertiary)', marginLeft: 6 }}>{description}</span>}
      </span>
    </label>
  )
}

// ── Button helpers (shared across pages) ─────────────────────────────────────

interface BtnProps {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  disabled?: boolean
  loading?: boolean
  type?: 'button' | 'submit'
}

export function Btn({ children, onClick, variant = 'ghost', size, disabled, loading, type = 'button' }: BtnProps) {
  return (
    <button
      type={type}
      className={`${styles.btn} ${variant === 'primary' ? styles.btnPrimary : ''} ${variant === 'ghost' ? styles.btnGhost : ''} ${variant === 'danger' ? styles.btnDanger : ''} ${size === 'sm' ? styles.btnSm : ''}`}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? 'Please wait…' : children}
    </button>
  )
}

// ── MemberRow ─────────────────────────────────────────────────────────────────

export function MemberRow({
  name,
  subtitle,
  badges,
  actions,
}: {
  name: string
  subtitle?: string
  badges?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className={styles.memberRow}>
      <div className={styles.memberAvatar}>{name[0]?.toUpperCase() ?? '?'}</div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <span className={styles.memberName} style={{ flex: 'unset' }}>{name}</span>
        {subtitle && (
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {subtitle}
          </span>
        )}
      </div>
      {badges && <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>{badges}</div>}
      {actions && <div className={styles.memberActions}>{actions}</div>}
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M2 2l12 12M14 2L2 14" />
    </svg>
  )
}