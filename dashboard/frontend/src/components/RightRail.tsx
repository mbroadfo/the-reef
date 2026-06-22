import { useEffect, useState } from 'react'
import { fetchTrades, fetchMarket } from '../api'
import type { Trade, MarketData } from '../types'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'
import SharkAvatar from './SharkAvatar'

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

export default function RightRail() {
  const [trades, setTrades]   = useState<Trade[]>([])
  const [market, setMarket]   = useState<MarketData | null>(null)

  useEffect(() => {
    const loadTrades = () => fetchTrades(8).then(r => setTrades(r.trades)).catch(() => {})
    loadTrades()
    const id = setInterval(loadTrades, 30_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const loadMarket = () => fetchMarket().then(setMarket).catch(() => {})
    loadMarket()
    const id = setInterval(loadMarket, 300_000)
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

      {/* ── VIX ── */}
      {market && (() => {
        const vix = market.vix.current
        const regime = vix === 0 ? 'No Data' : vix < 15 ? 'Low Vol' : vix < 20 ? 'Normal' : vix < 30 ? 'Elevated' : 'Fear'
        const vixColor = vix === 0 ? '#64748b' : vix < 15 ? 'var(--reef-gain)' : vix < 20 ? '#f1f5f9' : vix < 30 ? '#f59e0b' : 'var(--reef-loss)'
        const pctColor = market.vix.pct_change >= 0 ? 'var(--reef-loss)' : 'var(--reef-gain)'
        return (
          <div>
            <div className="flex justify-between items-center mb-3">
              <span className="text-xs font-sans uppercase tracking-widest text-slate-500">
                Volatility Index
              </span>
            </div>
            <div style={{
              background: 'var(--reef-elevated)',
              border: '1px solid var(--reef-border)',
              borderRadius: '8px',
              padding: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
            }}>
              <div>
                <div style={{ fontSize: '9px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '4px' }}>VIX</div>
                <div style={{ fontSize: '30px', fontWeight: 800, fontFamily: FONT_MONO, color: vixColor, lineHeight: 1 }}>
                  {vix > 0 ? vix.toFixed(2) : '—'}
                </div>
                {vix > 0 && (
                  <div style={{ fontSize: '12px', fontFamily: FONT_MONO, fontWeight: 600, color: pctColor, marginTop: '2px' }}>
                    {market.vix.pct_change >= 0 ? '+' : ''}{market.vix.pct_change.toFixed(2)}%
                  </div>
                )}
              </div>
              <div style={{
                padding: '5px 12px', borderRadius: '6px', fontFamily: FONT_SANS, fontSize: '13px', fontWeight: 700,
                color: vixColor, border: `1px solid ${vixColor}30`, background: `${vixColor}12`,
              }}>
                {regime}
              </div>
            </div>
          </div>
        )
      })()}

    </div>
  )
}
