import type { Trade } from '../types'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'
import SharkAvatar from './SharkAvatar'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function fmtDate(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function TradeDetails({ trade }: { trade: Trade | null }) {
  if (!trade) {
    return (
      <div className="card flex items-center justify-center h-28 text-slate-500 text-sm font-sans">
        No closed trades yet
      </div>
    )
  }

  const pnl = trade.pnl ?? 0
  const sharkName = normalizeSharkName(trade.surfaced_by || 'Apex Shark')
  const color = getSharkColor(sharkName)
  const entryPrice = trade.price
  const exitPrice = trade.exit_price ?? trade.price
  const pnlPct = entryPrice > 0 ? ((exitPrice - entryPrice) / entryPrice * 100) : 0
  const conviction = trade.conviction ?? 0
  const isGain = pnl >= 0

  return (
    <div className="card p-4">
      <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '10px' }}>
        Trade Details
      </div>

      {/* Ticker badge + shark header */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', marginBottom: '12px' }}>
        {/* Large ticker badge */}
        <div style={{
          width: '72px', height: '72px', borderRadius: '10px', flexShrink: 0,
          border: `2px solid ${color}`,
          background: `linear-gradient(135deg, ${color}18 0%, ${color}06 100%)`,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: '2px',
        }}>
          <div style={{ fontSize: trade.ticker.length > 4 ? '13px' : '18px', fontWeight: 800, fontFamily: FONT_MONO, color: '#f1f5f9', lineHeight: 1 }}>
            {trade.ticker}
          </div>
          <div style={{
            fontSize: '9px', fontFamily: FONT_SANS, fontWeight: 700, letterSpacing: '0.05em',
            color: isGain ? 'var(--reef-gain)' : 'var(--reef-loss)',
            background: isGain ? 'rgba(0,255,136,0.12)' : 'rgba(239,68,68,0.12)',
            padding: '1px 5px', borderRadius: '3px',
          }}>
            {trade.action}
          </div>
        </div>

        {/* Shark + P&L */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
            <SharkAvatar name={sharkName} size="sm" />
            <span style={{ fontSize: '11px', fontFamily: FONT_SANS, color, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {sharkName}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <div style={{
              fontSize: '22px', fontWeight: 800, fontFamily: FONT_MONO,
              color: isGain ? 'var(--reef-gain)' : 'var(--reef-loss)',
              lineHeight: 1,
            }}>
              {isGain ? '+' : ''}${Math.abs(pnl).toFixed(2)}
            </div>
            <div style={{ fontSize: '13px', fontFamily: FONT_MONO, fontWeight: 600, color: isGain ? 'var(--reef-gain)' : 'var(--reef-loss)' }}>
              {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
            </div>
          </div>
        </div>
      </div>

      {/* Entry / Exit / Date */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginBottom: '10px' }}>
        {[
          { label: 'Entry', value: `$${entryPrice.toFixed(2)}`, mono: true },
          { label: 'Exit',  value: `$${exitPrice.toFixed(2)}`,  mono: true },
          { label: 'Date',  value: fmtDate(trade.exit_time ?? trade.timestamp), mono: false },
        ].map(({ label, value, mono }) => (
          <div key={label}>
            <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '2px' }}>{label}</div>
            <div style={{ fontSize: mono ? '13px' : '11px', fontFamily: mono ? FONT_MONO : FONT_SANS, color: '#f1f5f9', fontWeight: mono ? 600 : 400 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Conviction bar */}
      <div style={{ marginBottom: trade.apex_rationale ? '10px' : 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Conviction
          </span>
          <span style={{ fontSize: '10px', fontFamily: FONT_MONO, color }}>{conviction}/10</span>
        </div>
        <div style={{ height: '4px', background: 'var(--reef-border)', borderRadius: '2px', overflow: 'hidden' }}>
          <div style={{ width: `${conviction * 10}%`, height: '100%', background: color, borderRadius: '2px' }} />
        </div>
      </div>

      {/* Rationale */}
      {trade.apex_rationale && (
        <div style={{
          fontSize: '11px', color: '#64748b', fontFamily: FONT_SANS, lineHeight: 1.55,
          borderTop: '1px solid var(--reef-border)', paddingTop: '8px', marginTop: '10px',
        }}>
          {trade.apex_rationale.slice(0, 200)}{trade.apex_rationale.length > 200 ? '…' : ''}
        </div>
      )}
    </div>
  )
}
