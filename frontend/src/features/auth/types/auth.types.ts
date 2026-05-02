export interface User {
  id: string
  email: string
  display_name: string
  avatar_url: string | null
  github_user_id: string | null
  google_user_id: string | null
  created_at: string
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  display_name: string
  password: string
}

export type OAuthProvider = 'github' | 'google'