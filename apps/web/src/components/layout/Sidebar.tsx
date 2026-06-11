import { NavLink } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import {
  LayoutDashboard,
  Settings,
  LogOut,
  ChevronsLeft,
  ChevronsRight,
  TrendingUp,
  ListChecks,
} from 'lucide-react';

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/review-queue', icon: ListChecks, label: 'Review Queue' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar({ collapsed, onToggle }: Props) {
  const { user, logout } = useAuth();

  const initials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : user?.user_id?.slice(0, 2).toUpperCase() || 'AI';

  return (
    <aside
      className="flex flex-col h-full"
      style={{
        width: collapsed ? 'var(--sidebar-collapsed)' : 'var(--sidebar-width)',
        minWidth: collapsed ? 'var(--sidebar-collapsed)' : 'var(--sidebar-width)',
        background: 'var(--bg-primary)',
        borderRight: '1px solid var(--border-primary)',
        transition: 'width 0.2s ease, min-width 0.2s ease',
        overflow: 'hidden',
      }}
    >
      {/* Brand */}
      <div
        className="flex items-center gap-3 px-5"
        style={{
          height: 'var(--topbar-height)',
          borderBottom: '1px solid var(--border-primary)',
        }}
      >
        <div
          className="flex items-center justify-center flex-shrink-0"
          style={{
            width: 28,
            height: 28,
            borderRadius: 'var(--radius-sm)',
            background: '#ffffff',
            color: '#000000',
          }}
        >
          <TrendingUp size={14} strokeWidth={2.5} />
        </div>
        {!collapsed && (
          <div style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>
              AIBAA
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', fontFamily: "'JetBrains Mono', monospace" }}>
              Investment Banking
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 flex flex-col gap-0.5">
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => 'flex items-center gap-3 px-3 py-2 rounded no-underline transition-colors duration-150 ' +
              (isActive ? 'text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]')
            }
            style={({ isActive }) => ({
              background: isActive ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
              justifyContent: collapsed ? 'center' : 'flex-start',
              borderRadius: 'var(--radius-sm)',
            })}
          >
            <item.icon size={16} strokeWidth={1.8} style={{ flexShrink: 0 }} />
            {!collapsed && (
              <span style={{ fontSize: 13, fontWeight: 500 }}>{item.label}</span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Collapse Toggle */}
      <button
        onClick={onToggle}
        className="mx-3 mb-2 flex items-center justify-center py-2 cursor-pointer"
        style={{
          background: 'transparent',
          border: '1px solid var(--border-primary)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text-muted)',
          transition: 'color 0.15s ease',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-secondary)' }}
        onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
      >
        {collapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
      </button>

      {/* User Card */}
      <div
        className="px-3 pb-3"
        style={{ borderTop: '1px solid var(--border-primary)', paddingTop: 12 }}
      >
        <div
          className="flex items-center gap-3 px-3 py-2"
          style={{
            justifyContent: collapsed ? 'center' : 'flex-start',
          }}
        >
          <div
            className="flex items-center justify-center flex-shrink-0"
            style={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: '#ffffff',
              color: '#000000',
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.03em',
            }}
          >
            {initials}
          </div>

          {!collapsed && (
            <div className="flex-1 min-w-0">
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.email || user?.user_id || 'User'}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontFamily: "'JetBrains Mono', monospace" }}>
                {user?.role || 'analyst'}
              </div>
            </div>
          )}

          {!collapsed && (
            <button
              onClick={logout}
              title="Sign out"
              className="cursor-pointer flex items-center justify-center"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                padding: 4,
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.color = 'var(--negative)' }}
              onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <LogOut size={13} />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
