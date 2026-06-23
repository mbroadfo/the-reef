import { useEffect, useState } from 'react'
import { fetchPositions, fetchTrades, fetchMarket } from '../api'
import type { Position, Trade, MarketData } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function relativeTime(ts: string): string {
  const mins = Math.floor((Date.now() - new Date(ts).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function SectionHeader({ children }: { children: string }) {
  return (
    <div style={{
      fontSize: '10px', fontFamily: FONT_SANS, fontWeight: 700,
      textTransform: 'uppercase', letterSpacing: '0.1em', color: '#334155',
      marginBottom: '8px',
    }}>
      {children}
    </div>
  )
}

function PositionRow({ pos }: { pos: Position }) {
  const pnlColor = pos.unrealized_pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)'
  const stopDist = pos.stop_loss && pos.current_price
    ? (pos.current_price - pos.stop_loss) / pos.current_price * 100
    : null

  return (
    <div style={{ padding: '10px 0', borderBottom: '1px solid #0f1929' }}>
      {/* Row 1: ticker + current price + P&L $ */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
        <span style={{ fontSize: '15px', fontFamily: FONT_MONO, fontWeight: 800, color: '#f1f5f9' }}>
          {pos.ticker}
        </span>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span style={{ fontSize: '13px', fontFamily: FONT_MONO, color: '#94a3b8' }}>
            ${pos.current_price.toFixed(2)}
          </span>
          <span style={{ fontSize: '14px', fontFamily: FONT_MONO, fontWeight: 700, color: pnlColor }}>
            {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(0)}
          </span>
        </div>
      </div>
      {/* Row 2: shares + entry + pnl % */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '3px' }}>
        <span style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#64748b' }}>
          {pos.shares} sh · entry ${pos.entry_price.toFixed(2)}
        </span>
        <span style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 700, color: pnlColor }}>
          {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(1)}%
        </span>
      </div>
      {/* Row 3: stop buffer */}
      {stopDist !== null && (
        <div style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#475569' }}>
          Stop ${pos.stop_loss?.toFixed(2)} · {stopDist.toFixed(1)}% buffer
        </div>
      )}
    </div>
  )
}

function TradeRow({ trade, last }: { trade: Trade; last: boolean }) {
  const isBuy = trade.action === 'BUY'
  const badgeColor = isBuy
    ? { text: '#3b82f6', border: 'rgba(59,130,246,0.35)', bg: 'rgba(59,130,246,0.1)' }
    : { text: '#f59e0b', border: 'rgba(245,158,11,0.35)', bg: 'rgba(245,158,11,0.1)' }

  return (
    <div style={{
      display: 'flex', gap: '10px', alignItems: 'center',
      padding: '9px 0',
      borderBottom: last ? 'none' : '1px solid #0f1929',
    }}>
      {/* Badge */}
      <div style={{
        width: '38px', textAlign: 'center', flexShrink: 0,
        fontSize: '10px', fontFamily: FONT_MONO, fontWeight: 800,
        color: badgeColor.text,
        border: `1px solid ${badgeColor.border}`,
        background: badgeColor.bg,
        borderRadius: '4px', padding: '3px 0',
      }}>
        {trade.action}
      </div>

      {/* Ticker + time */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '14px', fontFamily: FONT_MONO, fontWeight: 800, color: '#e2e8f0' }}>
          {trade.ticker}
        </div>
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#475569' }}>
          {relativeTime(trade.timestamp)}
        </div>
      </div>

      {/* Price + P&L */}
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 600, color: '#94a3b8' }}>
          ${trade.price.toFixed(2)}
        </div>
        {trade.pnl !== null && (
          <div style={{
            fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 700,
            color: trade.pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
          }}>
            {trade.pnl >= 0 ? '+' : ''}${Math.abs(trade.pnl).toFixed(0)}
          </div>
        )}
      </div>
    </div>
  )
}

export default function RightRail() {
  const [positions, setPositions] = useState<Position[]>([])
  const [trades, setTrades]       = useState<Trade[]>([])
  const [market, setMarket]       = useState<MarketData | null>(null)

  useEffect(() => {
    const load = () => {
      fetchPositions().then(setPositions).catch(() => {})
      fetchTrades(6).then(r => setTrades(r.trades)).catch(() => {})
    }
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    fetchMarket().then(setMarket).catch(() => {})
    const id = setInterval(() => fetchMarket().then(setMarket).catch(() => {}), 300_000)
    return () => clearInterval(id)
  }, [])

  const vix = market?.vix
  const vixColor = !vix || vix.current === 0 ? '#64748b'
    : vix.current < 15 ? 'var(--reef-gain)'
    : vix.current < 20 ? '#f1f5f9'
    : vix.current < 30 ? '#f59e0b'
    : 'var(--reef-loss)'
  const regime = !vix || vix.current === 0 ? 'No Data'
    : vix.current < 15 ? 'Low Vol'
    : vix.current < 20 ? 'Normal'
    : vix.current < 30 ? 'Elevated'
    : 'Fear'

  return (
    <div
      className="bg-reef-card border-l border-reef-border h-full"
      style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 0' }}>

        {/* Open Positions */}
        <SectionHeader>Open Positions</SectionHeader>
        {positions.length === 0 ? (
          <div style={{ fontSize: '12px', color: '#475569', fontFamily: FONT_SANS, padding: '8px 0 16px' }}>No open positions</div>
        ) : (
          <div style={{ marginBottom: '16px' }}>
            {positions.map(p => <PositionRow key={p.ticker} pos={p} />)}
          </div>
        )}

        {/* Recent Trades */}
        <SectionHeader>Recent Trades</SectionHeader>
        {trades.length === 0 ? (
          <div style={{ fontSize: '12px', color: '#475569', fontFamily: FONT_SANS, padding: '8px 0' }}>No trades yet</div>
        ) : (
          <div>
            {trades.map((t, i) => <TradeRow key={t.id} trade={t} last={i === trades.length - 1} />)}
          </div>
        )}
      </div>

      {/* VIX — pinned to bottom */}
      {vix && (
        <div style={{
          flexShrink: 0,
          padding: '10px 14px',
          borderTop: '1px solid var(--reef-border)',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <div>
            <div style={{ fontSize: '9px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#334155', marginBottom: '1px' }}>VIX</div>
            <div style={{ fontSize: '20px', fontWeight: 800, fontFamily: FONT_MONO, color: vixColor, lineHeight: 1 }}>
              {vix.current > 0 ? vix.current.toFixed(2) : '—'}
            </div>
            {vix.current > 0 && (
              <div style={{ fontSize: '10px', fontFamily: FONT_MONO, color: vix.pct_change >= 0 ? 'var(--reef-loss)' : 'var(--reef-gain)' }}>
                {vix.pct_change >= 0 ? '+' : ''}{vix.pct_change.toFixed(2)}%
              </div>
            )}
          </div>
          <div style={{
            padding: '4px 12px', borderRadius: '5px', fontFamily: FONT_SANS, fontSize: '12px', fontWeight: 700,
            color: vixColor, border: `1px solid ${vixColor}30`, background: `${vixColor}12`,
          }}>
            {regime}
          </div>
        </div>
      )}
    </div>
  )
}
