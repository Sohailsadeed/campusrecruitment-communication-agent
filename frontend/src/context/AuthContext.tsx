import React, { createContext, useContext, useState, useEffect } from "react";
import { UserOut, LoginPayload, RegisterPayload, loginUser, registerUser, getMe } from "../api/auth";

interface AuthContextType {
  user: UserOut | null;
  token: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  isAuthModalOpen: boolean;
  openAuthModal: () => void;
  closeAuthModal: () => void;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("speakflow_token"));
  const [user, setUser] = useState<UserOut | null>(() => {
    const cached = localStorage.getItem("speakflow_user");
    return cached ? JSON.parse(cached) : null;
  });
  const [loading, setLoading] = useState(true);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem("speakflow_token");
      if (storedToken) {
        try {
          const profile = await getMe();
          setUser(profile);
          localStorage.setItem("speakflow_user", JSON.stringify(profile));
        } catch {
          // Token expired or invalid
          localStorage.removeItem("speakflow_token");
          localStorage.removeItem("speakflow_user");
          setToken(null);
          setUser(null);
        }
      }
      setLoading(false);
    };
    initAuth();
  }, []);

  const login = async (payload: LoginPayload) => {
    const res = await loginUser(payload);
    localStorage.setItem("speakflow_token", res.access_token);
    localStorage.setItem("speakflow_user", JSON.stringify(res.user));
    setToken(res.access_token);
    setUser(res.user);
    setIsAuthModalOpen(false);
  };

  const register = async (payload: RegisterPayload) => {
    const res = await registerUser(payload);
    localStorage.setItem("speakflow_token", res.access_token);
    localStorage.setItem("speakflow_user", JSON.stringify(res.user));
    setToken(res.access_token);
    setUser(res.user);
    setIsAuthModalOpen(false);
  };

  const logout = () => {
    localStorage.removeItem("speakflow_token");
    localStorage.removeItem("speakflow_user");
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    if (localStorage.getItem("speakflow_token")) {
      try {
        const profile = await getMe();
        setUser(profile);
        localStorage.setItem("speakflow_user", JSON.stringify(profile));
      } catch {
        // Ignored
      }
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        loading,
        isAuthModalOpen,
        openAuthModal: () => setIsAuthModalOpen(true),
        closeAuthModal: () => setIsAuthModalOpen(false),
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
