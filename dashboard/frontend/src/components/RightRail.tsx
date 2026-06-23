import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
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
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: '10px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#475569', marginBottom: '10px' }}>
      {children}
    </div>
  )
}

function PositionsPanel({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return <div style={{ fontSize: '11px', color: '#475569', fontFamily: FONT_SANS, padding: '8px 0' }}>No open positions</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {positions.map((p, i) => {
        const pnlColor = p.unrealized_pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)'
        const stopDist = p.stop_loss && p.current_price
          ? ((p.current_price - p.stop_loss) / p.current_price * 100)
          : null
        return (
          <div
            key={p.ticker}
            style={{
              padding: '8px 0',
              borderBottom: i < positions.length - 1 ? '1px solid var(--reef-border)' : 'none',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '3px' }}>
              <span style={{ fontSize: '13px', fontFamily: FONT_MONO, fontWeight: 800, color: '#f1f5f9' }}>
                {p.ticker}
              </span>
              <span style={{ fontSize: '13px', fontFamily: FONT_MONO, fontWeight: 700, color: pnlColor }}>
                {p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl.toFixed(2)}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#64748b' }}>
                {p.shares} sh @ ${p.entry_price.toFixed(2)}
              </span>
              <span style={{ fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 600, color: pnlColor }}>
                {p.unrealized_pnl_pct >= 0 ? '+' : ''}{p.unrealized_pnl_pct.toFixed(1)}%
              </span>
            </div>
            {stopDist !== null && (
              <div style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#475569', marginTop: '2px' }}>
                Stop ${p.stop_loss?.toFixed(2)} · {stopDist.toFixed(1)}% away
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function TradesPanel({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) {
    return <div style={{ fontSize: '11px', color: '#475569', fontFamily: FONT_SANS, padding: '8px 0' }}>No trades yet</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {trades.map((t, i) => {
        const isBuy = t.action === 'BUY'
        return (
          <div
            key={t.id}
            style={{
              display: 'flex', gap: '8px', alignItems: 'center',
              padding: '7px 0',
              borderBottom: i < trades.length - 1 ? '1px solid var(--reef-border)' : 'none',
            }}
          >
            <div style={{
              width: '36px', textAlign: 'center', flexShrink: 0,
              fontSize: '9px', fontFamily: FONT_MONO, fontWeight: 700,
              color: isBuy ? '#3b82f6' : '#f59e0b',
              border: `1px solid ${isBuy ? 'rgba(59,130,246,0.3)' : 'rgba(245,158,11,0.3)'}`,
              background: isBuy ? 'rgba(59,130,246,0.08)' : 'rgba(245,158,11,0.08)',
              borderRadius: '3px', padding: '2px 0',
            }}>
              {t.action}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 700, color: '#f1f5f9' }}>
                {t.ticker}
              </div>
              <div style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#475569' }}>
                {relativeTime(t.timestamp)}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: '11px', fontFamily: FONT_MONO, color: '#64748b' }}>
                ${t.price.toFixed(2)}
              </div>
              {t.pnl !== null && (
                <div style={{ fontSize: '10px', fontFamily: FONT_MONO, fontWeight: 600, color: t.pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)' }}>
                  {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}
                </div>
              )}
            </div>
          </div>
        )
      })}
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
      fetchTrades(5).then(r => setTrades(r.trades)).catch(() => {})
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
    <div className="bg-reef-card border-l border-reef-border overflow-y-auto p-4 flex flex-col gap-5 h-full">

      {/* Open Positions */}
      <div>
        <SectionLabel>Open Positions</SectionLabel>
        <PositionsPanel positions={positions} />
      </div>

      <div style={{ borderTop: '1px solid var(--reef-border)' }} />

      {/* Recent Trades */}
      <div>
        <SectionLabel>Recent Trades</SectionLabel>
        <TradesPanel trades={trades} />
      </div>

      <div style={{ borderTop: '1px solid var(--reef-border)', marginTop: 'auto' }} />

      {/* VIX strip */}
      {vix && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingTop: '4px' }}>
          <div>
            <div style={{ fontSize: '9px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#475569' }}>VIX</div>
            <div style={{ fontSize: '22px', fontWeight: 800, fontFamily: FONT_MONO, color: vixColor, lineHeight: 1 }}>
              {vix.current > 0 ? vix.current.toFixed(2) : '—'}
            </div>
            {vix.current > 0 && (
              <div style={{ fontSize: '10px', fontFamily: FONT_MONO, color: vix.pct_change >= 0 ? 'var(--reef-loss)' : 'var(--reef-gain)' }}>
                {vix.pct_change >= 0 ? '+' : ''}{vix.pct_change.toFixed(2)}%
              </div>
            )}
          </div>
          <div style={{
            padding: '3px 10px', borderRadius: '5px', fontFamily: FONT_SANS, fontSize: '11px', fontWeight: 700,
            color: vixColor, border: `1px solid ${vixColor}30`, background: `${vixColor}12`,
          }}>
            {regime}
          </div>
        </div>
      )}

    </div>
  )
}
