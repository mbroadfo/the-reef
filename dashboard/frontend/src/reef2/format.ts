export const usd = (v: string | number | null | undefined, signed = false): string => {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  const s = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${n < 0 ? '-' : signed && n > 0 ? '+' : ''}$${s}`
}
export const pct = (v: number | null | undefined, digits = 1, signed = true): string =>
  v === null || v === undefined || Number.isNaN(v) ? '-' : `${signed && v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
export const num = (v: number | null | undefined, digits = 2): string =>
  v === null || v === undefined || Number.isNaN(v) ? '-' : v.toFixed(digits)
export const dayLabel = (d: string): string =>
  new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
export const tone = (v: number | string | null | undefined): string =>
  Number(v) > 0 ? 'text-gain' : Number(v) < 0 ? 'text-loss' : 'text-slate-300'

// Plain-English reason for a decline, shown next to the machine code.
export const REASON: Record<string, string> = {
  D0_RANK_CAP: 'Outranked',
  SIZE_ZERO: 'Too small to size',
  RISK_REJECTED: 'Risk Engine refused',
  INSTRUMENT_NOT_TRADABLE: 'Not tradable',
  PENDING_CASH_DEAL: 'Pending cash buyout',
  BOOK_UNTRUSTED: 'Book untrusted',
  POSITION_CAP: 'Position cap',
  SECTOR_CAP: 'Sector cap',
}
export const reasonLabel = (codes: string[]): string => codes.map(c => REASON[c] ?? c).join(' + ')
