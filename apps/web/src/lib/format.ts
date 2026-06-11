/**
 * Shared number and string formatting utilities.
 *
 * These were previously copy-pasted into DCFResultsView and LBOResultsView.
 * Import from here to keep formatting consistent across all result views.
 */

type Numeric = number | null | undefined

/** Format a number with optional decimal places and Indian currency abbreviations (Cr/L/B). */
export function fmt(n: Numeric | unknown, decimals = 0): string {
  if (n === null || n === undefined || n === '') return '—'
  const num = Number(n)
  if (isNaN(num)) return String(n)
  if (Math.abs(num) >= 1e9) return `${(num / 1e9).toFixed(1)}B`
  if (Math.abs(num) >= 1e7) return `${(num / 1e7).toFixed(1)} Cr`
  if (Math.abs(num) >= 1e5) return `${(num / 1e5).toFixed(1)}L`
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** Format a decimal ratio as a percentage string (0.045 → "4.5%"). */
export function pct(n: Numeric | unknown): string {
  if (n === null || n === undefined) return '—'
  const num = Number(n)
  if (isNaN(num)) return '—'
  return `${(num * 100).toFixed(1)}%`
}

/** Format a plain percentage number (45.2 → "45.2%"). */
export function pctRaw(n: Numeric | unknown): string {
  if (n === null || n === undefined) return '—'
  const num = Number(n)
  if (isNaN(num)) return '—'
  return `${num.toFixed(1)}%`
}

/** Format a number as a currency string (e.g. "Rs 4.5 Cr"). */
export function currency(n: Numeric | unknown, cur = 'Rs '): string {
  if (n === null || n === undefined) return '—'
  return `${cur}${fmt(n, 2)}`
}

/** Format a number as a multiple string (e.g. "12.3x"). */
export function multiple(n: Numeric | unknown): string {
  if (n === null || n === undefined) return '—'
  const num = Number(n)
  if (isNaN(num)) return '—'
  return `${num.toFixed(2)}x`
}

/** Convert a snake_case or UPPER_CASE label to Title Case, fixing known abbreviations. */
export function titleCase(label: string): string {
  return label
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .replace('Tgr', 'TGR')
    .replace('Wacc', 'WACC')
    .replace('Ebitda', 'EBITDA')
    .replace('Ev', 'EV')
    .replace('Irr', 'IRR')
    .replace('Moic', 'MOIC')
}
