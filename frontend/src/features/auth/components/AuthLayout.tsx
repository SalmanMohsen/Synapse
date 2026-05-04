import { type ReactNode } from 'react'
import styles from './AuthLayout.module.css'

interface Props {
  children: ReactNode
}

export default function AuthLayout({ children }: Props) {
  return (
    <div className={styles.root}>
      {/* ── Left panel — branding ── */}
      <div className={styles.panel}>
        <div className={styles.panelInner}>
          {/* Grid texture overlay */}
          <div className={styles.grid} aria-hidden />
          {/* Glow orb */}
          <div className={styles.orb} aria-hidden />

          <div className={styles.brand}>
            <Logo />
            <span className={styles.brandName}>Synapse</span>
          </div>

          <div className={styles.tagline}>
            <h1 className={styles.headline}>
              Humans deliberate.<br />
              Agents execute.<br />
              <span className={styles.headlineAccent}>Humans review.</span>
            </h1>
            <p className={styles.sub}>
              AI-native developer collaboration. Every thread is a live workspace.
            </p>
          </div>

          <div className={styles.pillRow}>
            <Pill>Observer Agent</Pill>
            <Pill>Planning Agent</Pill>
            <Pill>Code Agent</Pill>
          </div>

          <div className={styles.flowPreview} aria-hidden>
            {FLOW_STEPS.map((step, i) => (
              <div key={i} className={styles.flowStep} style={{ animationDelay: `${i * 120}ms` }}>
                <span className={styles.flowIndex}>{String(i + 1).padStart(2, '0')}</span>
                <span className={styles.flowText}>{step}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right panel — form ── */}
      <div className={styles.form}>
        <div className={styles.formInner}>
          {children}
        </div>
      </div>
    </div>
  )
}

const FLOW_STEPS = [
  'Team discusses in thread',
  'AI detects consensus',
  'Plan reviewed & approved',
  'Code written & tested',
  'PR opened for review',
]

function Pill({ children }: { children: ReactNode }) {
  return <span className={styles.pill}>{children}</span>
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="7" fill="rgba(99,102,241,0.15)" />
      <rect x="0.5" y="0.5" width="27" height="27" rx="6.5" stroke="rgba(99,102,241,0.4)" />
      <circle cx="9" cy="14" r="2.5" fill="#6366f1" />
      <circle cx="19" cy="14" r="2.5" fill="#6366f1" opacity="0.5" />
      <path d="M11.5 14 Q14 9 16.5 14" stroke="#6366f1" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <path d="M11.5 14 Q14 19 16.5 14" stroke="#6366f1" strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.4" />
    </svg>
  )
}