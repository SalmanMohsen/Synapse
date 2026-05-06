import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useLogout } from '@/features/auth/hooks/useAuth'
import styles from './LandingPage.module.css'

export default function LandingPage() {
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()
  const navigate = useNavigate()

  return (
    <div className={styles.page}>

      {/* ── Navbar ── */}
      <header className={styles.navbar}>
        <div className={styles.navInner}>
          <span className={styles.logo}>Synapse</span>

          <nav className={styles.navRight}>
            {user ? (
              <>
                <div className={styles.userInfo}>
                  {user.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt=""
                      className={styles.avatar}
                    />
                  ) : (
                    <div className={styles.avatarFallback}>
                      {user.display_name?.[0]?.toUpperCase() ?? '?'}
                    </div>
                  )}
                  <span className={styles.displayName}>{user.display_name}</span>
                </div>
                <button
                  className={styles.btnGhost}
                  onClick={() => logout.mutate()}
                  disabled={logout.isPending}
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <button
                  className={styles.btnGhost}
                  onClick={() => navigate('/login')}
                >
                  Sign in
                </button>
                <button
                  className={styles.btnPrimary}
                  onClick={() => navigate('/register')}
                >
                  Get started
                </button>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* ── Hero ── */}
      <main className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.badge}>AI-native developer collaboration</div>
          <h1 className={styles.headline}>
            Humans deliberate.<br />
            Agents execute.<br />
            Humans review.
          </h1>
          <p className={styles.subheadline}>
            Synapse watches your team's technical discussions in real time,
            detects consensus, and opens a pull request — with human approval
            at every step.
          </p>
          {!user && (
            <div className={styles.heroCta}>
              <button
                className={styles.btnPrimary}
                onClick={() => navigate('/register')}
              >
                Start building
              </button>
              <button
                className={styles.btnGhost}
                onClick={() => navigate('/login')}
              >
                Sign in
              </button>
            </div>
          )}
        </div>
      </main>

      {/* ── Feature grid ── */}
      <section className={styles.features}>
        {FEATURES.map((f) => (
          <div key={f.title} className={styles.featureCard}>
            <span className={styles.featureIcon}>{f.icon}</span>
            <h3 className={styles.featureTitle}>{f.title}</h3>
            <p className={styles.featureBody}>{f.body}</p>
          </div>
        ))}
      </section>

    </div>
  )
}

const FEATURES = [
  {
    icon: '⬡',
    title: 'Observer agent',
    body: 'A fine-tuned classifier reads every message and detects the moment your team reaches consensus — no manual triggers.',
  },
  {
    icon: '⊹',
    title: 'Automated implementation',
    body: 'A planning agent generates a step-by-step plan, spins an isolated Docker container, writes the code, and opens a PR.',
  },
  {
    icon: '◈',
    title: 'Six approval gates',
    body: 'Nothing automated proceeds without a prior human decision. You stay in control at every critical step of the pipeline.',
  },
  {
    icon: '⌥',
    title: 'Discipline channels',
    body: 'Frontend, Backend, Database, DevOps, AI — every channel carries the right specialty context for the agent that picks up the work.',
  },
]