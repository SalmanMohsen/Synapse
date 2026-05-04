import { type ButtonHTMLAttributes, type ReactNode } from 'react'
import styles from './Button.module.css'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  loading?: boolean
  variant?: 'primary' | 'ghost' | 'oauth'
  fullWidth?: boolean
}

export default function Button({
  children,
  loading = false,
  variant = 'primary',
  fullWidth = false,
  disabled,
  className = '',
  ...props
}: ButtonProps) {
  return (
    <button
      className={`
        ${styles.btn}
        ${styles[variant]}
        ${fullWidth ? styles.fullWidth : ''}
        ${loading ? styles.loading : ''}
        ${className}
      `.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span className={styles.spinner} aria-hidden />
      ) : null}
      <span className={loading ? styles.contentHidden : styles.content}>
        {children}
      </span>
    </button>
  )
}