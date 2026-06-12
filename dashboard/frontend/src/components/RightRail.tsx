import { useEffect, useState } from 'react'
import { fetchTrades } from '../api'
import type { Trade } from '../types'
import { getSharkColor, getSharkInitials, normalizeSharkName } from '../utils/sharks'

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

function heatBg(pct: number): string {
  if (pct > 1)    return 'bg-green-900/60'
  if (pct > 0.5)  return 'bg-green-900/40'
  if (pct > 0)    return 'bg-green-900/20'
  if (pct > -0.2) return 'bg-red-900/20'
  return 'bg-red-900/30'
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
              const initials = getSharkInitials(name)
              const pnl = trade.pnl

              return (
                <div
                  key={trade.id}
                  className="flex gap-3 items-start py-3 border-b border-reef-border last:border-0"
                >
                  {/* Avatar */}
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 bg-reef-elevated border-2 text-xs font-bold"
                    style={{ borderColor: color, color }}
                  >
                    {initials}
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
            <div key={sector} className={`p-3 rounded-lg ${heatBg(pct)}`}>
              <div className="text-xs text-slate-400">{sector}</div>
              <div className={`font-mono text-sm ${pct >= 0 ? 'text-gain' : 'text-loss'}`}>
                {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
