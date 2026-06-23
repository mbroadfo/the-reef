import { useEffect, useRef, useState } from 'react'
import { fetchMarket, fetchNominations } from '../api'
import type { Holding, Nomination } from '../types'

const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

interface TapeItem {
  ticker: string
  pct?: number
  label?: string
  isHolding: boolean
}

function TapeChip({ item }: { item: TapeItem }) {
  const color = item.isHolding
    ? item.pct! >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)'
    : '#64748b'

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '0 20px', whiteSpace: 'nowrap' }}>
      <span style={{
        fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 700,
        color: item.isHolding ? '#f1f5f9' : '#475569',
      }}>
        {item.ticker}
      </span>
      {item.isHolding && item.pct !== undefined ? (
        <span style={{ fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 600, color }}>
          {item.pct >= 0 ? '+' : ''}{item.pct.toFixed(2)}%
        </span>
      ) : (
        <span style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#475569' }}>
          {item.label ?? 'watchlist'}
        </span>
      )}
      <span style={{ color: '#1e293b', marginLeft: '12px' }}>·</span>
    </span>
  )
}

export default function TickerTape() {
  const [holdings, setHoldings]       = useState<Holding[]>([])
  const [nominations, setNominations] = useState<Nomination[]>([])
  const trackRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchMarket().then(m => setHoldings(m.holdings)).catch(() => {})
    fetchNominations().then(setNominations).catch(() => {})
  }, [])

  const items: TapeItem[] = [
    ...holdings.map(h => ({ ticker: h.ticker, pct: h.daily_pct, isHolding: true })),
    ...nominations.map(n => ({ ticker: n.ticker, label: n.source, isHolding: false })),
  ]

  if (items.length === 0) return null

  // Duplicate items so the scroll loop is seamless
  const allItems = [...items, ...items, ...items]
  const duration = Math.max(20, items.length * 4)

  return (
    <div style={{
      width: '100%',
      background: 'var(--reef-elevated)',
      borderTop: '1px solid var(--reef-border)',
      borderBottom: '1px solid var(--reef-border)',
      overflow: 'hidden',
      height: '32px',
      display: 'flex',
      alignItems: 'center',
      position: 'relative',
    }}>
      {/* Fade edges */}
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: '48px', zIndex: 1,
        background: 'linear-gradient(to right, var(--reef-elevated), transparent)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', right: 0, top: 0, bottom: 0, width: '48px', zIndex: 1,
        background: 'linear-gradient(to left, var(--reef-elevated), transparent)',
        pointerEvents: 'none',
      }} />

      <div
        ref={trackRef}
        style={{
          display: 'flex',
          animation: `ticker-scroll ${duration}s linear infinite`,
          willChange: 'transform',
        }}
      >
        {allItems.map((item, i) => <TapeChip key={i} item={item} />)}
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
