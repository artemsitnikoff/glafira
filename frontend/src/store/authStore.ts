import { create } from 'zustand';
import type { UserMe } from '@/api/aliases';

interface AuthState {
  accessToken: string | null;
  user: UserMe | null;

  setAuth: (token: string, user: UserMe) => void;
  setToken: (token: string) => void;
  setUser: (user: UserMe) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  setAuth: (token, user) => set({ accessToken: token, user }),
  setToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),
  logout: () => set({ accessToken: null, user: null }),
}));

// Computed selector — не store-property (Zustand не любит computed в state).
export const selectIsAuthenticated = (s: AuthState) => !!s.accessToken && !!s.user;