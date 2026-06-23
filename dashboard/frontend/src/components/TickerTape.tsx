import { useEffect, useState } from 'react'
import { fetchPositions, fetchNominations } from '../api'
import type { Position, Nomination } from '../types'

const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

function Divider() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', padding: '0 16px', color: '#1e293b', userSelect: 'none' }}>
      ◆
    </span>
  )
}

function HoldingChip({ pos }: { pos: Position }) {
  const pnlColor = pos.unrealized_pnl_pct >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '0 18px', whiteSpace: 'nowrap' }}>
      <span style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 800, color: '#f1f5f9' }}>
        {pos.ticker}
      </span>
      <span style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 600, color: '#94a3b8' }}>
        ${pos.current_price.toFixed(2)}
      </span>
      <span style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 700, color: pnlColor }}>
        {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(1)}%
      </span>
    </span>
  )
}

function WatchlistChip({ ticker }: { ticker: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '0 14px', whiteSpace: 'nowrap' }}>
      <span style={{ fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 600, color: '#475569' }}>
        {ticker}
      </span>
    </span>
  )
}

export default function TickerTape() {
  const [positions, setPositions]     = useState<Position[]>([])
  const [nominations, setNominations] = useState<Nomination[]>([])

  useEffect(() => {
    fetchPositions().then(setPositions).catch(() => {})
    fetchNominations().then(setNominations).catch(() => {})
    const id = setInterval(() => {
      fetchPositions().then(setPositions).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  if (positions.length === 0 && nominations.length === 0) return null

  const watchlistTickers = nominations.map(n => n.ticker)

  // Build one loop unit: holdings · WATCHLIST label · nominations
  const unit = (
    <>
      {positions.map(p => <HoldingChip key={p.ticker} pos={p} />)}
      {nominations.length > 0 && (
        <>
          <Divider />
          <span style={{ fontSize: '9px', fontFamily: FONT_SANS, fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.1em', padding: '0 8px' }}>
            Watchlist
          </span>
          {watchlistTickers.map(t => <WatchlistChip key={t} ticker={t} />)}
          <Divider />
        </>
      )}
    </>
  )

  const duration = Math.max(20, (positions.length + nominations.length) * 3)

  return (
    <div style={{
      width: '100%',
      background: 'var(--reef-elevated)',
      borderTop: '1px solid var(--reef-border)',
      borderBottom: '1px solid var(--reef-border)',
      overflow: 'hidden',
      height: '34px',
      display: 'flex',
      alignItems: 'center',
      position: 'relative',
    }}>
      <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '40px', zIndex: 1, background: 'linear-gradient(to right, var(--reef-elevated), transparent)', pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: '40px', zIndex: 1, background: 'linear-gradient(to left, var(--reef-elevated), transparent)', pointerEvents: 'none' }} />

      <div style={{ display: 'flex', animation: `ticker-scroll ${duration}s linear infinite`, willChange: 'transform' }}>
        {/* Triple-repeat for seamless loop */}
        {unit}{unit}{unit}
      </div>

      <style>{`
        @keyframes ticker-scroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-33.333%); }
        }
      `}</style>
    </div>
  )
}
