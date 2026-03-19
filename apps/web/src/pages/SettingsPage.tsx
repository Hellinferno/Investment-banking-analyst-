import { useAuth } from '../components/auth/AuthContext';
import { Navigate } from 'react-router-dom';

export default function SettingsPage() {
  const { user, logout, isAuthenticated } = useAuth();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#0A0A0A',
        color: '#F0F0F0',
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        padding: '40px 32px',
      }}
    >
      <div style={{ maxWidth: 720 }}>
        <h1
          style={{
            fontSize: 18,
            fontWeight: 700,
            marginBottom: 32,
            color: '#F0F0F0',
            borderBottom: '1px solid #333',
            paddingBottom: 16,
          }}
        >
          Settings
        </h1>

        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 13, color: '#888', marginBottom: 16, textTransform: 'uppercase', letterSpacing: '1px' }}>
            Account
          </h2>
          <div
            style={{
              background: '#111111',
              border: '1px solid #333',
              borderRadius: 4,
              padding: 20,
            }}
          >
            <div style={{ display: 'grid', gap: 12 }}>
              {[
                { label: 'User ID', value: user.user_id },
                { label: 'Tenant', value: user.tenant_id },
                { label: 'Role', value: user.role },
                { label: 'Email', value: user.email || 'N/A' },
              ].map(({ label, value }) => (
                <div key={label} style={{ display: 'flex', gap: 16 }}>
                  <span style={{ color: '#888', fontSize: 12, width: 80 }}>{label}</span>
                  <span style={{ color: '#F0F0F0', fontSize: 12 }}>{value}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 13, color: '#888', marginBottom: 16, textTransform: 'uppercase', letterSpacing: '1px' }}>
            Session
          </h2>
          <div
            style={{
              background: '#111111',
              border: '1px solid #333',
              borderRadius: 4,
              padding: 20,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <p style={{ color: '#F0F0F0', fontSize: 13, margin: 0 }}>
                  Current session active
                </p>
                <p style={{ color: '#666', fontSize: 11, margin: '4px 0 0' }}>
                  Token ID: {user.token_id || 'N/A'}
                </p>
              </div>
              <button
                onClick={handleLogout}
                style={{
                  padding: '8px 16px',
                  background: '#2A0A0A',
                  border: '1px solid #5A2020',
                  borderRadius: 3,
                  color: '#FF6B6B',
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                Sign Out
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
