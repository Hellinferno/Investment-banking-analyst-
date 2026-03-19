import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './components/auth/AuthContext';
import { AuthGuard } from './components/auth/AuthGuard';
import LoginPage from './pages/LoginPage';
import SettingsPage from './pages/SettingsPage';
import Dashboard from './pages/Dashboard';
import DealWorkspace from './pages/DealWorkspace';
import { useEffect } from 'react';
import { api } from './lib/api';

function BootstrappedApp() {
  const { user, isLoading, login, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (isAuthenticated) {
      api.defaults.headers.common['Authorization'] = `Bearer ${localStorage.getItem('aibaa_token') || ''}`;
    }
  }, [isAuthenticated, isLoading]);

  const handleLogin = async (token: string) => {
    localStorage.setItem('aibaa_token', token);
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    await login(token);
  };

  return (
    <Routes>
      <Route
        path="/login"
        element={
          isAuthenticated ? (
            <Navigate to="/" replace />
          ) : (
            <LoginPage onLogin={handleLogin} />
          )
        }
      />
      <Route
        path="/"
        element={
          <AuthGuard>
            <Dashboard />
          </AuthGuard>
        }
      />
      <Route
        path="/deals/:dealId"
        element={
          <AuthGuard>
            <DealWorkspace />
          </AuthGuard>
        }
      />
      <Route
        path="/settings"
        element={
          <AuthGuard>
            <SettingsPage />
          </AuthGuard>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <BootstrappedApp />
      </AuthProvider>
    </BrowserRouter>
  );
}

