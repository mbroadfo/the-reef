import { useEffect, useState } from 'react'
import { fetchPositions, fetchNominations } from '../api'
import type { Position, Nomination } from '../types'

const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

const DEFAULT_WATCHLIST = [
  "NVDA", "AMD", "AVGO", "ARM", "TSM", "META", "PLTR",
  "COIN", "MSTR", "MARA", "HOOD",
  "RKLB", "ASTS", "TSLA", "SMCI", "SPCX",
]

function Divider() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', padding: '0 16px', color: '#334155', userSelect: 'none' }}>
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
      <span style={{ fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 600, color: '#94a3b8' }}>
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

  // Always show — use DEFAULT_WATCHLIST as static fill
  const nominatedTickers = nominations.map(n => n.ticker)
  const positionTickers  = new Set(positions.map(p => p.ticker))

  // Watchlist = nominated tickers + DEFAULT_WATCHLIST not already in positions/nominations
  const extraWatchlist = DEFAULT_WATCHLIST.filter(
    t => !positionTickers.has(t) && !nominatedTickers.includes(t)
  )
  const allWatchlist = [...nominatedTickers, ...extraWatchlist]

  if (positions.length === 0 && allWatchlist.length === 0) return null

  // Build one loop unit: holdings · WATCHLIST label · watchlist
  const unit = (
    <>
      {positions.map(p => <HoldingChip key={p.ticker} pos={p} />)}
      {allWatchlist.length > 0 && (
        <>
          <Divider />
          <span style={{ fontSize: '9px', fontFamily: FONT_SANS, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em', padding: '0 8px' }}>
            Watchlist
          </span>
          {allWatchlist.map(t => <WatchlistChip key={t} ticker={t} />)}
          <Divider />
        </>
      )}
    </>
  )

  const duration = Math.max(30, (positions.length + allWatchlist.length) * 2)

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
