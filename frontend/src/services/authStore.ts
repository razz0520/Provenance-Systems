import { create } from "zustand";

export interface User {
  id: string;
  email: string;
  role: "ADMIN" | "PUBLISHER" | "VIEWER";
  organization_name: string;
  organization_domain: string;
  department?: string | null;
  designation?: string | null;
  public_key?: string | null;
  is_active: boolean;
  is_verified: boolean;
  mfa_enabled: boolean;
  login_count: number;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  theme: "light" | "dark";
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  toggleMobileSidebar: () => void;
  setAuth: (user: User, accessToken: string, refreshToken?: string) => void;
  updateUser: (user: Partial<User>) => void;
  logout: () => void;
  toggleTheme: () => void;
  initAuth: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  isLoading: true,
  theme: "light",
  mobileSidebarOpen: false,
  setMobileSidebarOpen: (open: boolean) => set({ mobileSidebarOpen: open }),
  toggleMobileSidebar: () => set((state) => ({ mobileSidebarOpen: !state.mobileSidebarOpen })),

  initAuth: () => {
    if (typeof window === "undefined") return;

    const token = localStorage.getItem("access_token");
    const rToken = localStorage.getItem("refresh_token");
    const userStr = localStorage.getItem("user_data");
    const savedTheme = (localStorage.getItem("theme") as "light" | "dark") || "light";

    if (savedTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }

    if (token && userStr) {
      try {
        const user = JSON.parse(userStr);
        set({
          user,
          accessToken: token,
          refreshToken: rToken,
          isAuthenticated: true,
          isLoading: false,
          theme: savedTheme,
        });
        return;
      } catch (e) {
        console.error("Failed to parse user data from localStorage", e);
      }
    }
    set({ isLoading: false, theme: savedTheme });
  },

  setAuth: (user, accessToken, refreshToken) => {
    localStorage.setItem("access_token", accessToken);
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
    localStorage.setItem("user_data", JSON.stringify(user));
    set({
      user,
      accessToken,
      refreshToken: refreshToken || null,
      isAuthenticated: true,
      isLoading: false,
    });
  },

  updateUser: (partialUser) => {
    const current = get().user;
    if (!current) return;
    const updated = { ...current, ...partialUser };
    localStorage.setItem("user_data", JSON.stringify(updated));
    set({ user: updated });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user_data");
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  },

  toggleTheme: () => {
    const nextTheme = get().theme === "light" ? "dark" : "light";
    localStorage.setItem("theme", nextTheme);
    if (nextTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    set({ theme: nextTheme });
  },
}));
