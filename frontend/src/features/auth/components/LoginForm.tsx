import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLogin } from '../hooks/useAuth'
import Input from './Input'
import Button from './Button'
import OAuthButtons from './OAuthButtons'
import Divider from './Divider'
import styles from './AuthForm.module.css'

export default function LoginForm() {
  const login = useLogin()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})

  const validate = () => {
    const errors: typeof fieldErrors = {}
    if (!email) errors.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email'
    if (!password) errors.password = 'Password is required'
    return errors
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const errors = validate()
    if (Object.keys(errors).length) { setFieldErrors(errors); return }
    setFieldErrors({})
    login.mutate({ email, password })
  }

  const serverError = login.error
    ? (login.error as any)?.response?.data?.detail ?? 'Invalid credentials'
    : null

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div className={styles.eyebrow}>Welcome back</div>
        <h2 className={styles.title}>Sign in to Synapse</h2>
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
          label="Email"
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          autoComplete="email"
          autoFocus
        />

        <Input
          label="Password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          autoComplete="current-password"
        />

        <Button
          type="submit"
          fullWidth
          loading={login.isPending}
        >
          Sign in
        </Button>
      </form>

      <p className={styles.switch}>
        No account?{' '}
        <Link to="/register" className={styles.link}>
          Create one
        </Link>
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