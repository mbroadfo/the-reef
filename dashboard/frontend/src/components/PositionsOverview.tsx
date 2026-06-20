import { useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import type { Position } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
const COLORS = ['#00ff88', '#3b82f6', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#ef4444', '#84cc16']


type View = 'symbol' | 'sector'

interface SliceData { name: string; value: number; pct: number; pnl_pct?: number }

export default function PositionsOverview({ positions }: { positions: Position[] }) {
  const [view, setView] = useState<View>('symbol')

  if (!positions.length) {
    return (
      <div className="card flex items-center justify-center h-40 text-slate-500 text-sm font-sans">
        No open positions
      </div>
    )
  }

  const total = positions.reduce((s, p) => s + p.market_value, 0)

  const bySymbol: SliceData[] = positions.map(p => ({
    name: p.ticker,
    value: p.market_value,
    pct: total > 0 ? (p.market_value / total * 100) : 0,
    pnl_pct: p.unrealized_pnl_pct,
  }))

  const sectorMap = new Map<string, number>()
  for (const p of positions) {
    const sector = p.sector ?? 'Other'
    sectorMap.set(sector, (sectorMap.get(sector) ?? 0) + p.market_value)
  }
  const bySector: SliceData[] = Array.from(sectorMap.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value, pct: total > 0 ? value / total * 100 : 0 }))

  const data = view === 'symbol' ? bySymbol : bySector

  return (
    <div className="card p-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Positions Overview
        </div>
        <div style={{ display: 'flex', gap: '2px' }}>
          {(['symbol', 'sector'] as View[]).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '10px',
                fontFamily: FONT_SANS,
                fontWeight: 600,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: view === v ? 'var(--reef-gain)' : 'var(--reef-border)',
                background: view === v ? 'rgba(0,255,136,0.12)' : 'transparent',
                color: view === v ? 'var(--reef-gain)' : '#64748b',
                textTransform: 'capitalize',
              }}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <ResponsiveContainer width={110} height={110}>
          <PieChart>
            <Pie
              data={data}
              cx="50%" cy="50%"
              innerRadius={34} outerRadius={52}
              dataKey="value"
              strokeWidth={0}
              isAnimationActive={false}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: number) => [`$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, '']}
              contentStyle={{ background: 'var(--reef-card)', border: '1px solid var(--reef-border)', borderRadius: '6px', fontSize: '11px' }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div style={{ flex: 1, minWidth: 0 }}>
          {data.map((d, i) => (
            <div
              key={d.name}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '3px 0',
                borderBottom: i < data.length - 1 ? '1px solid var(--reef-border)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', background: COLORS[i % COLORS.length], flexShrink: 0 }} />
                <span style={{ fontSize: '12px', fontFamily: FONT_MONO, color: '#f1f5f9', fontWeight: 700 }}>
                  {d.name}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', fontFamily: FONT_MONO, color: '#94a3b8' }}>
                  {d.pct.toFixed(1)}%
                </span>
                {d.pnl_pct !== undefined && (
                  <span style={{
                    fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 600,
                    color: d.pnl_pct >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
                  }}>
                    {d.pnl_pct >= 0 ? '+' : ''}{d.pnl_pct.toFixed(1)}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
