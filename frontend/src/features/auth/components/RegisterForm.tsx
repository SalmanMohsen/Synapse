import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRegister } from '../hooks/useAuth'
import Input from './Input'
import Button from './Button'
import OAuthButtons from './OAuthButtons'
import Divider from './Divider'
import styles from './AuthForm.module.css'

export default function RegisterForm() {
  const register = useRegister()

  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{
    display_name?: string; email?: string; password?: string
  }>({})

  const validate = () => {
    const errors: typeof fieldErrors = {}
    if (!displayName.trim() || displayName.trim().length < 2)
      errors.display_name = 'At least 2 characters'
    if (!email) errors.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
      errors.email = 'Enter a valid email'
    if (!password) errors.password = 'Password is required'
    else if (password.length < 8) errors.password = 'At least 8 characters'
    return errors
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const errors = validate()
    if (Object.keys(errors).length) { setFieldErrors(errors); return }
    setFieldErrors({})
    register.mutate({ display_name: displayName.trim(), email, password })
  }

  const serverError = register.error
    ? (register.error as any)?.response?.data?.detail ?? 'Registration failed'
    : null

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div className={styles.eyebrow}>Get started</div>
        <h2 className={styles.title}>Create your account</h2>
      </div>

      <OAuthButtons />

      <Divider />

      <form onSubmit={handleSubmit} className={styles.form} noValidate>
        {serverError && (
          <div className={styles.serverError} role="alert">
            <ErrorIcon />
            {serverError}
          </div>
        )}

        <Input
          label="Display name"
          type="text"
          placeholder="Ada Lovelace"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          error={fieldErrors.display_name}
          autoComplete="name"
          autoFocus
        />

        <Input
          label="Email"
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          autoComplete="email"
        />

        <Input
          label="Password"
          type="password"
          placeholder="Min. 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          autoComplete="new-password"
          hint="At least 8 characters"
        />

        <Button
          type="submit"
          fullWidth
          loading={register.isPending}
        >
          Create account
        </Button>
      </form>

      <p className={styles.switch}>
        Already have an account?{' '}
        <Link to="/login" className={styles.link}>
          Sign in
        </Link>
      </p>

      <p className={styles.terms}>
        By creating an account you agree to the{' '}
        <a href="#" className={styles.termsLink}>Terms of Service</a>
        {' '}and{' '}
        <a href="#" className={styles.termsLink}>Privacy Policy</a>.
      </p>
    </div>
  )
}

function ErrorIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-.75 3.75a.75.75 0 011.5 0v3.5a.75.75 0 01-1.5 0v-3.5zm.75 7a1 1 0 110-2 1 1 0 010 2z"/>
    </svg>
  )
}