import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/features/auth/store/authSlice'
import { useCurrentUser } from '@/features/auth/hooks/useAuth'
import { useToastStore } from '@/shared/hooks/useToast'
import { ToastContainer } from '@/shared/components'

// Auth pages (existing)
import LoginPage from '@/features/auth/pages/LoginPage'
import RegisterPage from '@/features/auth/pages/RegisterPage'
import LandingPage from '@/features/auth/pages/LandingPage'
import SettingsPage from '@/features/auth/pages/SettingsPage'

// New pages
import WorkspacePage from '@/features/workspace/pages/WorkspacePage'
import WorkspaceSettingsPage from '@/features/workspace/pages/WorkspaceSettingsPage'
import ProjectPage from '@/features/project/pages/ProjectPage'
import ProjectSettingsPage from '@/features/project/pages/ProjectSettingsPage'
import ChannelPage from '@/features/channel/pages/ChannelPage'
import InboxPage from '@/features/inbox/pages/InboxPage'

import ProtectedRoute from '@/router/ProtectedRoute'
import GuestRoute from '@/router/GuestRoute'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 5 * 60 * 1000 },
  },
})

function SessionBootstrap() {
  const setUser = useAuthStore((s) => s.setUser)
  useCurrentUser()
  useEffect(() => {
    const handler = () => setUser(null)
    window.addEventListener('auth:session-expired', handler)
    return () => window.removeEventListener('auth:session-expired', handler)
  }, [setUser])
  return null
}

function ToastMount() {
  const { toasts, dismiss } = useToastStore()
  return <ToastContainer toasts={toasts} onDismiss={dismiss} />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionBootstrap />
        <ToastMount />
        <Routes>
          {/* Guest-only */}
          <Route path="/login"    element={<GuestRoute><LoginPage /></GuestRoute>} />
          <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />

          {/* Protected */}
          <Route path="/"                           element={<ProtectedRoute><LandingPage /></ProtectedRoute>} />
          <Route path="/settings"                   element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/inbox"                      element={<ProtectedRoute><InboxPage /></ProtectedRoute>} />
          <Route path="/workspaces/:wid"            element={<ProtectedRoute><WorkspacePage /></ProtectedRoute>} />
          <Route path="/workspaces/:wid/settings"   element={<ProtectedRoute><WorkspaceSettingsPage /></ProtectedRoute>} />
          <Route path="/projects/:pid"              element={<ProtectedRoute><ProjectPage /></ProtectedRoute>} />
          <Route path="/projects/:pid/settings"     element={<ProtectedRoute><ProjectSettingsPage /></ProtectedRoute>} />
          <Route path="/channels/:cid"              element={<ProtectedRoute><ChannelPage /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}