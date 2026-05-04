import styles from './Divider.module.css'

export default function Divider({ label = 'or' }: { label?: string }) {
  return (
    <div className={styles.root} role="separator">
      <span className={styles.line} />
      <span className={styles.label}>{label}</span>
      <span className={styles.line} />
    </div>
  )
}