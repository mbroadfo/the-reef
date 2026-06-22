import { useEffect, useState } from 'react'
import { fetchTrades } from '../api'
import type { Trade } from '../types'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'
import SharkAvatar from './SharkAvatar'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

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

export default function RightRail() {
  const [trades, setTrades] = useState<Trade[]>([])

  useEffect(() => {
    const loadTrades = () => fetchTrades(8).then(r => setTrades(r.trades)).catch(() => {})
    loadTrades()
    const id = setInterval(loadTrades, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className="bg-reef-card border-l border-reef-border overflow-y-auto p-4 flex flex-col gap-6 h-full"
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
              const name   = normalizeSharkName(trade.surfaced_by || 'Apex Shark')
              const color  = getSharkColor(name)
              const pnl    = trade.pnl

              return (
                <div
                  key={trade.id}
                  className="flex gap-3 items-start py-3 border-b border-reef-border last:border-0"
                >
                  <SharkAvatar name={name} size="md" />

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

    </div>
  )
}
