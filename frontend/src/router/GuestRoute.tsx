import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useCurrentUser } from '@/features/auth/hooks/useAuth'

interface Props { children: ReactNode }

export default function GuestRoute({ children }: Props) {
  const user = useAuthStore((s) => s.user)
  const { isLoading } = useCurrentUser()

  if (isLoading) return null

  if (user) return <Navigate to="/" replace />

  return <>{children}</>
}