import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import type { Position } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
const COLORS = ['#00ff88', '#3b82f6', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#ef4444']

export default function PositionsOverview({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <div className="card flex items-center justify-center h-40 text-slate-500 text-sm font-sans">
        No open positions
      </div>
    )
  }

  const total = positions.reduce((s, p) => s + p.market_value, 0)
  const data = positions.map(p => ({
    name: p.ticker,
    value: p.market_value,
    pct: total > 0 ? (p.market_value / total * 100) : 0,
    pnl_pct: p.unrealized_pnl_pct,
  }))

  return (
    <div className="card p-4">
      <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '10px' }}>
        Positions Overview
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
              formatter={(v: number) => [`$${v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`, '']}
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
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', fontFamily: FONT_MONO, color: '#94a3b8' }}>
                  {d.pct.toFixed(1)}%
                </span>
                <span style={{
                  fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 600,
                  color: d.pnl_pct >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)',
                }}>
                  {d.pnl_pct >= 0 ? '+' : ''}{d.pnl_pct.toFixed(1)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
