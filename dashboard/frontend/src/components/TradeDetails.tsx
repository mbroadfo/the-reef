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

  return (
    <div className="card p-4">
      <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '10px' }}>
        Trade Details
      </div>

      {/* Ticker + shark row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <SharkAvatar name={sharkName} size="md" />
          <div>
            <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {sharkName}
            </div>
            <div style={{ fontSize: '22px', fontWeight: 800, fontFamily: FONT_MONO, color: '#f1f5f9', lineHeight: 1.1 }}>
              {trade.ticker}
            </div>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{
            fontSize: '20px', fontWeight: 800, fontFamily: FONT_MONO,
            color: pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
            lineHeight: 1,
          }}>
            {pnl >= 0 ? '+' : ''}${Math.abs(pnl).toFixed(2)}
          </div>
          <div style={{ fontSize: '12px', fontFamily: FONT_MONO, color: pnlPct >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)', marginTop: '2px' }}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Entry → Exit + date */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginBottom: '10px' }}>
        <div>
          <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Entry</div>
          <div style={{ fontSize: '13px', fontFamily: FONT_MONO, color: '#f1f5f9', fontWeight: 600 }}>${entryPrice.toFixed(2)}</div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Exit</div>
          <div style={{ fontSize: '13px', fontFamily: FONT_MONO, color: '#f1f5f9', fontWeight: 600 }}>${exitPrice.toFixed(2)}</div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Date</div>
          <div style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#94a3b8' }}>{fmtDate(trade.exit_time ?? trade.timestamp)}</div>
        </div>
      </div>

      {/* Conviction */}
      <div style={{ marginBottom: trade.apex_rationale ? '10px' : 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Conviction
          </span>
          <span style={{ fontSize: '10px', fontFamily: FONT_MONO, color }}>
            {conviction}/10
          </span>
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
