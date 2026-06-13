import { useEffect, useState } from 'react'
import { fetchTrades } from '../api'
import type { Trade } from '../types'
import { getSharkColor, getSharkFilter, normalizeSharkName } from '../utils/sharks'
import sharkImg from '../assets/shark-base.png'

const HEAT_MAP = [
  { sector: 'Technology',  pct: +1.24 },
  { sector: 'Financials',  pct: +0.82 },
  { sector: 'Healthcare',  pct: -0.15 },
  { sector: 'Consumer',    pct: +1.05 },
  { sector: 'Industrials', pct: +0.45 },
  { sector: 'Energy',      pct: -0.21 },
]

function relativeTime(ts: string): string {
  const mins = Math.floor((Date.now() - new Date(ts).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}

function heatStyle(pct: number) {
  if (pct > 1)    return { background: 'rgba(0,255,136,0.22)', border: '0.5px solid rgba(0,255,136,0.3)' }
  if (pct > 0.5)  return { background: 'rgba(0,255,136,0.14)' }
  if (pct > 0)    return { background: 'rgba(0,255,136,0.07)' }
  if (pct > -0.5) return { background: 'rgba(255,68,68,0.12)' }
  return { background: 'rgba(255,68,68,0.20)', border: '0.5px solid rgba(255,68,68,0.25)' }
}

export default function RightRail() {
  const [trades, setTrades] = useState<Trade[]>([])

  useEffect(() => {
    const load = () => fetchTrades(8).then(r => setTrades(r.trades)).catch(() => {})
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className="bg-reef-card border-l border-reef-border overflow-y-auto p-4 flex flex-col gap-6"
      style={{ gridColumn: '3', gridRow: '2' }}
    >
      {/* ── Shark Activity Feed ── */}
      <div>
        <div className="flex justify-between items-center mb-3">
          <span className="text-xs font-sans uppercase tracking-widest text-slate-500">
            Shark Activity Feed
          </span>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-reef-elevated border border-reef-border">
            <div className="w-1.5 h-1.5 rounded-full bg-reef-gain animate-pulse" />
            <span className="text-xs text-reef-gain">Live</span>
          </div>
        </div>

        {trades.length === 0 ? (
          <div className="text-xs text-slate-600 py-6 text-center">No trades yet</div>
        ) : (
          <div>
            {trades.map(trade => {
              const name  = normalizeSharkName(trade.surfaced_by || 'Apex Shark')
              const color = getSharkColor(name)
              const filter = getSharkFilter(name)
              const pnl = trade.pnl

              return (
                <div
                  key={trade.id}
                  className="flex gap-3 items-start py-3 border-b border-reef-border last:border-0"
                >
                  {/* Avatar */}
                  <div style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    border: `2px solid ${color}`,
                    background: 'var(--reef-elevated)',
                    overflow: 'hidden',
                    flexShrink: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <img
                      src={sharkImg}
                      alt={name}
                      style={{
                        width: '90%',
                        height: '90%',
                        objectFit: 'contain',
                        filter,
                        mixBlendMode: 'screen',
                      }}
                    />
                  </div>

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-sans font-semibold truncate" style={{ color }}>
                      {name}
                    </div>
                    <div className="text-xs text-slate-400">
                      {trade.action === 'BUY' ? 'Bought' : 'Sold'} {trade.ticker}
                    </div>
                    <div className="text-xs text-slate-500">
                      {relativeTime(trade.timestamp)}
                    </div>
                  </div>

                  {/* P&L badge (sells only) */}
                  {pnl !== null && pnl !== undefined && (
                    <div className={`text-xs font-mono font-semibold shrink-0 ${pnl >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── Market Heat Map ── */}
      <div>
        <div className="text-xs font-sans uppercase tracking-widest text-slate-500 mb-3">
          Market Heat Map
        </div>
        {/* TODO Phase 4: wire to real sector data */}
        <div className="grid grid-cols-2 gap-2">
          {HEAT_MAP.map(({ sector, pct }) => (
            <div
              key={sector}
              style={{
                ...heatStyle(pct),
                padding: '10px',
                borderRadius: '8px',
                minHeight: '56px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{
                fontSize: '10px',
                fontFamily: "'Space Grotesk', system-ui, sans-serif",
                fontWeight: '600',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: '#94a3b8',
              }}>
                {sector}
              </div>
              <div style={{
                fontSize: '14px',
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                fontWeight: '700',
                color: pct >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
              }}>
                {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
