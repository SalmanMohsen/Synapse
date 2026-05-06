import { api } from '@/shared/lib/axios'
import type { LoginPayload, RegisterPayload, User } from '../types/auth.types'

export const authApi = {
  register: (data: RegisterPayload): Promise<User> =>
    api.post<User>('/auth/register', data).then((r) => r.data),

  login: (data: LoginPayload): Promise<User> =>
    api.post<User>('/auth/login', data).then((r) => r.data),

  logout: (): Promise<void> =>
    api.post('/auth/logout').then(() => undefined),

  getMe: (): Promise<User> =>
    api.get<User>('/auth/me').then((r) => r.data),

  unlinkGithub: (): Promise<User> =>
    api.delete<User>('/auth/link/github').then((r) => r.data),

  unlinkGoogle: (): Promise<User> =>
    api.delete<User>('/auth/link/google').then((r) => r.data),

  // OAuth sign-in — browser navigates to the backend directly so cookies are
  // set on the backend origin, not proxied through Vite.
  oauthUrl: (provider: 'github' | 'google'): string =>
    `${import.meta.env.VITE_API_URL}/api/v1/auth/${provider}`,

  // Linking — same popup pattern but different backend route
  linkUrl: (provider: 'github' | 'google'): string =>
    `${import.meta.env.VITE_API_URL}/api/v1/auth/link/${provider}`,
}