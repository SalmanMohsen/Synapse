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
      setUser(null)
      queryClient.clear()
      navigate('/login')
    },
  })
}

// ── OAuth popup — sign in / register ─────────────────────────────────────────
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
      window.location.href = authApi.oauthUrl(provider)
      return
    }

    const handleMessage = async (event: MessageEvent) => {
      if (event.origin !== import.meta.env.VITE_API_URL) return

      window.removeEventListener('message', handleMessage)
      clearInterval(closedPoller)

      if (event.data?.type === 'oauth_success') {
        const user = await authApi.getMe()
        setUser(user)
        queryClient.setQueryData(['me'], user)
        navigate('/')
      }

      if (event.data?.type === 'oauth_error') {
        console.error('OAuth error:', event.data.reason)
        // TODO: surface as toast
      }
    }

    window.addEventListener('message', handleMessage)

    const closedPoller = setInterval(() => {
      if (popup.closed) {
        clearInterval(closedPoller)
        window.removeEventListener('message', handleMessage)
      }
    }, 500)
  }

  return { open }
}

// ── OAuth popup — account linking ─────────────────────────────────────────────
//
// Same popup pattern as sign-in but points to /auth/link/:provider.
// The backend posts 'link_success' or 'link_error' instead of 'oauth_success'.
// On success we re-fetch /me so the store reflects the newly linked provider.

export const useLinkProvider = () => {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()

  const link = (provider: OAuthProvider): Promise<void> => {
    return new Promise((resolve, reject) => {
      const popup = window.open(
        authApi.linkUrl(provider),
        'synapse-link',
        'width=600,height=700,scrollbars=yes,resizable=yes',
      )

      if (!popup) {
        reject(new Error('Popup was blocked. Please allow popups for this site.'))
        return
      }

      const handleMessage = async (event: MessageEvent) => {
        if (event.origin !== import.meta.env.VITE_API_URL) return

        window.removeEventListener('message', handleMessage)
        clearInterval(closedPoller)

        if (event.data?.type === 'link_success') {
          // Re-fetch to get updated github_user_id / google_user_id on user
          const user = await authApi.getMe()
          setUser(user)
          queryClient.setQueryData(['me'], user)
          resolve()
        }

        if (event.data?.type === 'link_error') {
          reject(new Error(event.data.reason ?? 'Linking failed'))
        }
      }

      window.addEventListener('message', handleMessage)

      const closedPoller = setInterval(() => {
        if (popup.closed) {
          clearInterval(closedPoller)
          window.removeEventListener('message', handleMessage)
          // User closed popup without completing — resolve silently
          resolve()
        }
      }, 500)
    })
  }

  return { link }
}

// ── Unlink provider ───────────────────────────────────────────────────────────

export const useUnlinkProvider = () => {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (provider: OAuthProvider) =>
      provider === 'github' ? authApi.unlinkGithub() : authApi.unlinkGoogle(),
    onSuccess: (user) => {
      setUser(user)
      queryClient.setQueryData(['me'], user)
    },
  })
}