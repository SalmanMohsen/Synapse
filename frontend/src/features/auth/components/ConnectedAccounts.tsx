import { useState } from 'react'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useLinkProvider, useUnlinkProvider } from '@/features/auth/hooks/useAuth'
import type { OAuthProvider } from '@/features/auth/types/auth.types'
import styles from './ConnectedAccounts.module.css'

export default function ConnectedAccounts() {
  const user = useAuthStore((s) => s.user)
  const { link } = useLinkProvider()
  const unlink = useUnlinkProvider()
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<OAuthProvider | null>(null)

  const handleLink = async (provider: OAuthProvider) => {
    setError(null)
    setPending(provider)
    try {
      await link(provider)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setPending(null)
    }
  }

  const handleUnlink = (provider: OAuthProvider) => {
    setError(null)
    unlink.mutate(provider, {
      onError: (err: unknown) => {
        setError(err instanceof Error ? err.message : 'Something went wrong')
      },
    })
  }

  if (!user) return null

  const githubLinked = Boolean(user.github_user_id)
  const googleLinked = Boolean(user.google_user_id)

  return (
    <div className={styles.root}>
      <h2 className={styles.heading}>Connected accounts</h2>
      <p className={styles.subtitle}>
        Link additional sign-in methods to your account.
      </p>

      {error && <p className={styles.error}>{error}</p>}

      <ul className={styles.list}>
        {/* GitHub */}
        <li className={styles.item}>
          <div className={styles.providerInfo}>
            <GithubIcon />
            <div>
              <span className={styles.providerName}>GitHub</span>
              {githubLinked && (
                <span className={styles.linkedBadge}>Linked</span>
              )}
            </div>
          </div>
          {githubLinked ? (
            <button
              className={styles.btnDanger}
              onClick={() => handleUnlink('github')}
              disabled={unlink.isPending}
            >
              Unlink
            </button>
          ) : (
            <button
              className={styles.btnSecondary}
              onClick={() => handleLink('github')}
              disabled={pending === 'github'}
            >
              {pending === 'github' ? 'Connecting…' : 'Link GitHub'}
            </button>
          )}
        </li>

        {/* Google */}
        <li className={styles.item}>
          <div className={styles.providerInfo}>
            <GoogleIcon />
            <div>
              <span className={styles.providerName}>Google</span>
              {googleLinked && (
                <span className={styles.linkedBadge}>Linked</span>
              )}
            </div>
          </div>
          {googleLinked ? (
            <button
              className={styles.btnDanger}
              onClick={() => handleUnlink('google')}
              disabled={unlink.isPending}
            >
              Unlink
            </button>
          ) : (
            <button
              className={styles.btnSecondary}
              onClick={() => handleLink('google')}
              disabled={pending === 'google'}
            >
              {pending === 'google' ? 'Connecting…' : 'Link Google'}
            </button>
          )}
        </li>
      </ul>
    </div>
  )
}

function GithubIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2C6.477 2 2 6.484 2 12.021c0 4.428 2.865 8.184 6.839 9.504.5.092.682-.217.682-.482 0-.237-.009-.868-.013-1.703-2.782.605-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844a9.59 9.59 0 012.504.337c1.909-1.296 2.747-1.026 2.747-1.026.546 1.378.202 2.397.1 2.65.64.7 1.028 1.595 1.028 2.688 0 3.848-2.338 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0022 12.021C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  )
}