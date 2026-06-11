/**
 * Design token constants — single source of truth for inline styles.
 *
 * All values reference CSS variables defined in index.css so that theming
 * changes only need to happen in one place.
 */

export const COLORS = {
  // Backgrounds
  bgVoid: 'var(--bg-void)',
  bgPrimary: 'var(--bg-primary)',
  bgSurface: 'var(--bg-surface)',
  bgElevated: 'var(--bg-elevated)',
  bgCard: 'var(--bg-card)',
  bgInput: 'var(--bg-input)',
  bgHover: 'var(--bg-hover)',

  // Borders
  border: 'var(--border-primary)',
  borderSubtle: 'var(--border-subtle)',
  borderFocus: 'var(--border-focus)',

  // Text
  textPrimary: 'var(--text-primary)',
  textSecondary: 'var(--text-secondary)',
  textMuted: 'var(--text-muted)',
  textAccent: 'var(--text-accent)',

  // Accent
  accent: 'var(--accent)',
  accentLight: 'var(--accent-light)',

  // Semantic
  positive: 'var(--positive)',
  positiveBg: 'var(--positive-bg)',
  positiveBorder: 'var(--positive-border)',
  negative: 'var(--negative)',
  negativeBg: 'var(--negative-bg)',
  negativeBorder: 'var(--negative-border)',
  warning: 'var(--warning)',
  warningBg: 'var(--warning-bg)',
  warningBorder: 'var(--warning-border)',
  info: 'var(--info)',
  infoBg: 'var(--info-bg)',
  infoBorder: 'var(--info-border)',
} as const;

export const FONT_SIZE = {
  xs: '10px',
  sm: '11px',
  base: '13px',
  md: '14px',
  lg: '16px',
  xl: '20px',
  xxl: '24px',
} as const;

export const FONT_FAMILY = {
  sans: 'Inter, system-ui, sans-serif',
  mono: "'JetBrains Mono', 'SF Mono', Consolas, monospace",
} as const;

export const SPACING = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  xxl: '32px',
} as const;

export const RADIUS = {
  sm: 'var(--radius-sm)',
  md: 'var(--radius-md)',
  lg: 'var(--radius-lg)',
  xl: 'var(--radius-xl)',
} as const;
