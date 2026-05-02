import { create } from 'zustand'
import type { User } from '../types/auth.types'

interface AuthState {
  // The token never lives here — it's an httpOnly cookie the browser manages.
  // Zustand holds only the user object so components can read it without
  // prop drilling or calling useCurrentUser() everywhere.
  user: User | null
  setUser: (user: User | null) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
}))