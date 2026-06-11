/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { fetchCurrentUser, api, type CurrentUserInfo } from '../../lib/api';

interface AuthState {
  user: CurrentUserInfo | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    const token = localStorage.getItem('aibaa_token');
    if (!token) {
      queueMicrotask(() => { if (isMounted) setIsLoading(false); });
      return;
    }
    fetchCurrentUser(true)
      .then((u) => { if (isMounted) setUser(u); })
      .catch(() => {
        localStorage.removeItem('aibaa_token');
      })
      .finally(() => { if (isMounted) setIsLoading(false); });
    
    return () => { isMounted = false; };
  }, []);

  const login = useCallback(async (token: string) => {
    localStorage.setItem('aibaa_token', token);
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    const u = await fetchCurrentUser(true);
    setUser(u);
  }, []);

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout'); } catch { /* best-effort */ }
    localStorage.removeItem('aibaa_token');
    delete api.defaults.headers.common['Authorization'];
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
