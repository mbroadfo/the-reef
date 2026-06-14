import { useEffect, useState } from 'react'
import { fetchTrades, fetchSectors } from '../api'
import type { Trade, Sector } from '../types'
import { getSharkColor, getSharkFilter, normalizeSharkName } from '../utils/sharks'
import sharkImg from '../assets/shark-base.png'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

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
  const [trades, setTrades]   = useState<Trade[]>([])
  const [sectors, setSectors] = useState<Sector[]>([])

  useEffect(() => {
    const loadTrades = () => fetchTrades(8).then(r => setTrades(r.trades)).catch(() => {})
    loadTrades()
    const id = setInterval(loadTrades, 30_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const loadSectors = () => fetchSectors().then(setSectors).catch(() => {})
    loadSectors()
    const id = setInterval(loadSectors, 300_000)
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
              const name   = normalizeSharkName(trade.surfaced_by || 'Apex Shark')
              const color  = getSharkColor(name)
              const filter = getSharkFilter(name)
              const pnl    = trade.pnl

              return (
                <div
                  key={trade.id}
                  className="flex gap-3 items-start py-3 border-b border-reef-border last:border-0"
                >
                  <div style={{
                    width: '40px', height: '40px', borderRadius: '50%',
                    border: `2px solid ${color}`, background: 'var(--reef-elevated)',
                    overflow: 'hidden', flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <img
                      src={sharkImg}
                      alt={name}
                      style={{
                        width: '90%', height: '90%', objectFit: 'contain',
                        filter, mixBlendMode: 'screen',
                      }}
                    />
                  </div>

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

      {/* ── Market Heat Map ── */}
      <div>
        <div className="flex justify-between items-center mb-3">
          <span className="text-xs font-sans uppercase tracking-widest text-slate-500">
            Market Heat Map
          </span>
          <span style={{ fontSize: '11px', color: '#64748b', fontFamily: FONT_SANS, cursor: 'default' }}>
            Today ▾
          </span>
        </div>
        {(() => {
          const sorted = [...sectors].sort(
            (a, b) => Math.abs(b.pct_change) - Math.abs(a.pct_change)
          )
          const rows = [sorted.slice(0, 4), sorted.slice(4)].filter(r => r.length > 0)

          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              {rows.map((row, ri) => {
                const totalWeight = row.reduce(
                  (s, x) => s + Math.max(Math.abs(x.pct_change), 0.1), 0
                )
                const cols = row
                  .map(x => `${(Math.max(Math.abs(x.pct_change), 0.1) / totalWeight * 100).toFixed(1)}fr`)
                  .join(' ')
                return (
                  <div key={ri} style={{ display: 'grid', gridTemplateColumns: cols, gap: '3px' }}>
                    {row.map(s => (
                      <div
                        key={s.ticker}
                        style={{
                          border: '1px solid rgba(255,255,255,0.04)',
                          ...heatStyle(s.pct_change),
                          padding: '8px',
                          borderRadius: '6px',
                          minHeight: '52px',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div style={{
                          fontSize: '10px',
                          fontFamily: FONT_SANS,
                          fontWeight: '600',
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                          color: '#94a3b8',
                        }}>
                          {s.sector.split(' ')[0]}
                        </div>
                        <div style={{
                          fontSize: '13px',
                          fontFamily: FONT_MONO,
                          fontWeight: '700',
                          color: s.pct_change >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
                        }}>
                          {s.pct_change >= 0 ? '+' : ''}{s.pct_change.toFixed(2)}%
                        </div>
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>
          )
        })()}
      </div>
    </div>
  )
}
