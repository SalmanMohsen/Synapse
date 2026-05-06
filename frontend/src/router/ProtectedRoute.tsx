import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/authSlice'


interface Props {
  children: ReactNode
}

export default function ProtectedRoute({ children }: Props) {
  const user = useAuthStore((s) => s.user)


  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}