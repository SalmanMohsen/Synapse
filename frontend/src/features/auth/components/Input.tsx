import { forwardRef, type InputHTMLAttributes } from 'react'
import styles from './Input.module.css'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
  hint?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, id, ...props }, ref) => {
    const inputId = id ?? label.toLowerCase().replace(/\s+/g, '-')

    return (
      <div className={styles.field}>
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
        <div className={styles.inputWrap}>
          <input
            id={inputId}
            ref={ref}
            className={`${styles.input} ${error ? styles.inputError : ''}`}
            {...props}
          />
          <div className={styles.highlight} aria-hidden />
        </div>
        {error && (
          <span className={styles.error} role="alert">
            {error}
          </span>
        )}
        {hint && !error && (
          <span className={styles.hint}>{hint}</span>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'
export default Input