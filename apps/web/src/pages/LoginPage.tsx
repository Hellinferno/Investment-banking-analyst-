import { useState } from 'react';
import { authApi } from '../lib/api';

interface LoginProps {
  onLogin: (token: string) => void;
}

export default function LoginPage({ onLogin }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    const bootstrapToken = import.meta.env.VITE_API_TOKEN || 'dev-local-token';
    const role = import.meta.env.VITE_DEV_AUTH_ROLE || 'analyst';

    try {
      const res = await authApi.post<{
        success: boolean;
        data: { access_token: string };
      }>(
        '/auth/dev-token',
        { requested_role: role },
        { headers: { 'X-Dev-API-Token': bootstrapToken } }
      );

      if (res.data.success) {
        onLogin(res.data.data.access_token);
      } else {
        setError('Authentication failed. Please check your credentials.');
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error && err.message.includes('401')
          ? 'Invalid credentials'
          : 'Unable to connect to server. Please try again.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0A0A0A',
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      }}
    >
      <div
        style={{
          width: 400,
          padding: 40,
          background: '#111111',
          border: '1px solid #333333',
          borderRadius: 4,
        }}
      >
        <h1
          style={{
            color: '#F0F0F0',
            fontSize: 20,
            fontWeight: 700,
            marginBottom: 8,
            letterSpacing: '-0.5px',
          }}
        >
          AIBAA
        </h1>
        <p style={{ color: '#888888', fontSize: 12, marginBottom: 32 }}>
          AI Investment Banking Analyst Agent
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label
              style={{ display: 'block', color: '#888888', fontSize: 11, marginBottom: 6 }}
            >
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                background: '#0A0A0A',
                border: '1px solid #333333',
                borderRadius: 3,
                color: '#F0F0F0',
                fontSize: 13,
                outline: 'none',
                boxSizing: 'border-box',
              }}
              placeholder="analyst@aibaa.local"
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label
              style={{ display: 'block', color: '#888888', fontSize: 11, marginBottom: 6 }}
            >
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                background: '#0A0A0A',
                border: '1px solid #333333',
                borderRadius: 3,
                color: '#F0F0F0',
                fontSize: 13,
                outline: 'none',
                boxSizing: 'border-box',
              }}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div
              style={{
                padding: '8px 12px',
                background: '#2A0A0A',
                border: '1px solid #5A2020',
                borderRadius: 3,
                color: '#FF6B6B',
                fontSize: 12,
                marginBottom: 16,
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: '100%',
              padding: '10px 16px',
              background: isLoading ? '#333333' : '#1A56DB',
              border: 'none',
              borderRadius: 3,
              color: '#FFFFFF',
              fontSize: 13,
              fontWeight: 600,
              cursor: isLoading ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p
          style={{
            color: '#444444',
            fontSize: 10,
            marginTop: 24,
            textAlign: 'center',
          }}
        >
          For demo access, ensure VITE_API_TOKEN is set in your environment.
        </p>
      </div>
    </div>
  );
}
