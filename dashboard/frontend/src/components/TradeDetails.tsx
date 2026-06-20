import type { Trade } from '../types'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'
import SharkAvatar from './SharkAvatar'
import ConvictionBar from './ConvictionBar'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

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

  return (
    <div className="card p-4">
      <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '10px' }}>
        Last Trade
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span style={{ fontSize: '20px', fontWeight: 800, fontFamily: FONT_MONO, color: '#f1f5f9' }}>
            {trade.ticker}
          </span>
          <span style={{
            fontSize: '10px', fontFamily: FONT_SANS, padding: '2px 7px', borderRadius: '4px',
            background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.25)', fontWeight: 700,
          }}>
            SELL
          </span>
        </div>
        <div style={{
          fontSize: '18px', fontWeight: 800, fontFamily: FONT_MONO,
          color: pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
        }}>
          {pnl >= 0 ? '+' : ''}${Math.abs(pnl).toFixed(2)}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '10px' }}>
        <div>
          <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Entry</div>
          <div style={{ fontSize: '13px', fontFamily: FONT_MONO, color: '#f1f5f9' }}>${entryPrice.toFixed(2)}</div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#64748b', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Exit</div>
          <div style={{ fontSize: '13px', fontFamily: FONT_MONO, color: '#f1f5f9' }}>${exitPrice.toFixed(2)}</div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <SharkAvatar name={sharkName} size="sm" />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '12px', fontFamily: FONT_SANS, fontWeight: 600, color, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {sharkName}
          </div>
          <ConvictionBar value={trade.conviction} color={color} />
        </div>
      </div>

      {trade.apex_rationale && (
        <div style={{
          fontSize: '11px', color: '#64748b', fontFamily: FONT_SANS, lineHeight: 1.5,
          borderTop: '1px solid var(--reef-border)', paddingTop: '8px',
        }}>
          {trade.apex_rationale.slice(0, 140)}{trade.apex_rationale.length > 140 ? '…' : ''}
        </div>
      )}
    </div>
  )
}
