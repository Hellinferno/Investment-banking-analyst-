import { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { api } from '../../lib/api';
import { useEffect, useState } from 'react';

export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, isLoading, isAuthenticated } = useAuth();
  const location = useLocation();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('aibaa_token');
    if (stored && !isAuthenticated && !isLoading) {
      api.defaults.headers.common['Authorization'] = `Bearer ${stored}`;
    }
    setChecked(true);
  }, [isAuthenticated, isLoading]);

  if (!checked || isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#0A0A0A',
          color: '#888888',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 12,
        }}
      >
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

export function RoleGuard({ children, allowedRoles }: { children: ReactNode; allowedRoles: string[] }) {
  const { user } = useAuth();

  if (!user || !allowedRoles.includes(user.role)) {
    return (
      <div
        style={{
          padding: 24,
          color: '#FF6B6B',
          fontSize: 13,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        You do not have permission to view this page.
      </div>
    );
  }

  return <>{children}</>;
}
