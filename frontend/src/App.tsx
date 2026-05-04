import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useCurrentUser } from '@/features/auth/hooks/useAuth'
import { useAuthStore } from '@/features/auth/store/authSlice'
import LoginPage from '@/features/auth/pages/LoginPage'
import RegisterPage from '@/features/auth/pages/RegisterPage'
import ProtectedRoute from '@/router/ProtectedRoute'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 5 * 60 * 1000 },
  },
})

function SessionBootstrap() {
  const setUser = useAuthStore((s) => s.setUser)
  useCurrentUser()

  // Listen for session expiry dispatched by the Axios interceptor
  useEffect(() => {
    const handler = () => setUser(null)
    window.addEventListener('auth:session-expired', handler)
    return () => window.removeEventListener('auth:session-expired', handler)
  }, [setUser])

  return null
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionBootstrap />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/" element={<ProtectedRoute><DashboardPlaceholder /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

// Temporary placeholder — replaced in Phase 2
function DashboardPlaceholder() {
  const user = useAuthStore((s) => s.user)
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', flexDirection: 'column', gap: '12px',
      fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)',
      fontSize: '13px',
    }}>
      <div style={{ color: 'var(--brand)', fontSize: '11px', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
        authenticated
      </div>
      <div style={{ color: 'var(--text-primary)', fontSize: '15px' }}>
        Welcome, {user?.display_name}
      </div>
      <div style={{ color: 'var(--text-tertiary)' }}>{user?.email}</div>
    </div>
  )
}