import { useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceDot, ResponsiveContainer,
} from 'recharts'
import type { Snapshot } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

type Timescale = '1W' | '1M' | '3M' | 'All'
const TIMESCALES: Timescale[] = ['1W', '1M', '3M', 'All']

function cutoffMs(ts: Timescale): number | null {
  const now = Date.now()
  if (ts === '1W') return now - 7  * 86400000
  if (ts === '1M') return now - 30 * 86400000
  if (ts === '3M') return now - 90 * 86400000
  return null
}

function computeTicks(timestamps: string[], max: number): string[] {
  if (timestamps.length <= max) return timestamps
  const step = Math.ceil(timestamps.length / (max - 1))
  const ticks: string[] = []
  for (let i = 0; i < timestamps.length; i += step) ticks.push(timestamps[i])
  const last = timestamps[timestamps.length - 1]
  if (ticks[ticks.length - 1] !== last) ticks.push(last)
  return ticks
}

function fmtY(v: number): string {
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`
  return `$${v.toFixed(0)}`
}

interface TooltipPayload {
  value: number
  payload: { timestamp: string; event: string }
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const { value, payload: p } = payload[0]
  const d = new Date(p.timestamp)
  return (
    <div className="bg-reef-card border border-reef-border rounded-lg px-3 py-2 text-xs">
      <div className="text-slate-400 font-sans">
        {d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
      </div>
      <div className="text-white font-bold font-mono">
        ${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
      </div>
      {p.event && p.event !== 'daily' && (
        <div className={`font-sans uppercase font-semibold ${p.event === 'BUY' ? 'text-blue-400' : 'text-amber-400'}`}>
          {p.event}
        </div>
      )}
    </div>
  )
}

interface Props {
  snapshots: Snapshot[]
  startingCash: number
}

export default function PortfolioChart({ snapshots, startingCash }: Props) {
  const [ts, setTs] = useState<Timescale>('All')

  if (snapshots.length < 2) {
    return (
      <div className="card flex items-center justify-center h-48 text-slate-500 text-sm font-sans">
        Chart populates after first trade
      </div>
    )
  }

  const cutoff = cutoffMs(ts)
  const data = snapshots
    .filter(s => cutoff === null || new Date(s.timestamp).getTime() >= cutoff)
    .map(s => ({ timestamp: s.timestamp, portfolio_value: s.portfolio_value, event: s.event }))

  const ticks = computeTicks(data.map(d => d.timestamp), 6)
  const markers = data.filter(d => d.event === 'BUY' || d.event === 'SELL')

  return (
    <div className="card p-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Portfolio Growth
        </div>
        <div style={{ display: 'flex', gap: '4px' }}>
          {TIMESCALES.map(t => (
            <button
              key={t}
              onClick={() => setTs(t)}
              style={{
                padding: '3px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontFamily: FONT_SANS,
                fontWeight: 600,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: ts === t ? 'var(--reef-gain)' : 'var(--reef-border)',
                background: ts === t ? 'rgba(0,255,136,0.12)' : 'transparent',
                color: ts === t ? 'var(--reef-gain)' : '#64748b',
                transition: 'all 150ms',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gainGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#00ff88" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" vertical={false} />
          <XAxis
            dataKey="timestamp"
            ticks={ticks}
            tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'Space Grotesk' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={fmtY}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
            domain={[
              (dataMin: number) => Math.floor(dataMin * 0.995 / 100) * 100,
              (dataMax: number) => Math.ceil(dataMax * 1.005 / 100) * 100,
            ]}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            y={startingCash}
            stroke="var(--reef-border)"
            strokeDasharray="4 4"
            label={{ value: 'Start', fill: 'var(--reef-border)', fontSize: 10, position: 'insideTopLeft' }}
          />
          <Area
            type="monotone"
            dataKey="portfolio_value"
            stroke="#00ff88"
            strokeWidth={2}
            fill="url(#gainGrad)"
            dot={false}
            activeDot={{ r: 4, fill: '#00ff88' }}
            isAnimationActive={false}
          />
          {markers.map((m, i) => (
            <ReferenceDot
              key={i}
              x={m.timestamp}
              y={m.portfolio_value}
              r={4}
              fill={m.event === 'BUY' ? '#3b82f6' : '#f59e0b'}
              stroke="var(--reef-card)"
              strokeWidth={1.5}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
