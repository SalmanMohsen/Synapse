import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/authApi'
import { useAuthStore } from '../store/authSlice'
import type { LoginPayload, OAuthProvider, RegisterPayload } from '../types/auth.types'

// ── Session bootstrap ────────────────────────────────────────────────────────
//
// Called once in App.tsx. On load, the browser sends the httpOnly cookie
// automatically — if it's valid, we get the user back and hydrate Zustand.
// A 401 means no session exists; retry: false keeps it from spamming.

export const useCurrentUser = () => {
  const setUser = useAuthStore((s) => s.setUser)

  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const user = await authApi.getMe()
      setUser(user)
      return user
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Email / password ─────────────────────────────────────────────────────────

export const useLogin = () => {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: (data: LoginPayload) => authApi.login(data),
    onSuccess: (user) => {
      setUser(user)
      queryClient.setQueryData(['me'], user)
      navigate('/')
    },
  })
}

export const useRegister = () => {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: (data: RegisterPayload) => authApi.register(data),
    onSuccess: (user) => {
      setUser(user)
      queryClient.setQueryData(['me'], user)
      navigate('/')
    },
  })
}

export const useLogout = () => {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      // Clear regardless of whether the server call succeeded
      setUser(null)
      queryClient.clear()
      navigate('/login')
    },
  })
}

// ── OAuth popup ──────────────────────────────────────────────────────────────
//
// Opens a popup to the backend OAuth start URL. The backend redirects to
// GitHub/Google, handles the callback, sets the httpOnly cookies, and serves
// a tiny HTML page that posts a message back to this window then closes.

export const useOAuthPopup = () => {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const open = (provider: OAuthProvider) => {
    // window.open MUST be synchronous — any await before this line will cause
    // browsers to classify it as a non-user-gesture popup and block it.
    const popup = window.open(
      authApi.oauthUrl(provider),
      'synapse-oauth',
      'width=600,height=700,scrollbars=yes,resizable=yes',
    )

    if (!popup) {
      // Popup was blocked — fall back to full redirect
      window.location.href = authApi.oauthUrl(provider)
      return
    }

    const handleMessage = async (event: MessageEvent) => {
      // Strict origin check — only accept messages from the backend
      if (event.origin !== import.meta.env.VITE_API_URL) return

      window.removeEventListener('message', handleMessage)
      clearInterval(closedPoller)

      if (event.data?.type === 'oauth_success') {
        // Cookie is already set by the backend popup response.
        // Just fetch the user to hydrate state.
        const user = await authApi.getMe()
        setUser(user)
        queryClient.setQueryData(['me'], user)
        navigate('/')
      }

      if (event.data?.type === 'oauth_error') {
        console.error('OAuth error:', event.data.reason)
        // TODO: surface this as a toast notification
      }
    }

    window.addEventListener('message', handleMessage)

    // Clean up listener if the user closes the popup manually without completing
    const closedPoller = setInterval(() => {
      if (popup.closed) {
        clearInterval(closedPoller)
        window.removeEventListener('message', handleMessage)
      }
    }, 500)
  }

  return { open }
}