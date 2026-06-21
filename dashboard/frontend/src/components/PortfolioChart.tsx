import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceDot, ResponsiveContainer,
} from 'recharts'
import type { Snapshot } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

type Timescale = '1W' | '1M' | '3M' | 'All'
const TIMESCALES: Timescale[] = ['1W', '1M', '3M', 'All']

function getSlice(snapshots: Snapshot[], ts: Timescale): Snapshot[] {
  if (ts === 'All' || snapshots.length === 0) return snapshots
  const now = Date.now()
  const weekCutoff = now - 7 * 86400000
  const weekCount = snapshots.filter(s => new Date(s.timestamp).getTime() >= weekCutoff).length

  if (ts === '1W') {
    return snapshots.filter(s => new Date(s.timestamp).getTime() >= weekCutoff)
  }

  const days = ts === '1M' ? 30 : 90
  const cutoff = now - days * 86400000
  const dateFiltered = snapshots.filter(s => new Date(s.timestamp).getTime() >= cutoff)
  if (dateFiltered.length > weekCount) return dateFiltered

  const frac = ts === '1M' ? 0.30 : 0.65
  const count = Math.max(weekCount + 15, Math.ceil(snapshots.length * frac))
  return snapshots.slice(Math.max(0, snapshots.length - count))
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

function DiamondShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  const s = 6
  return (
    <polygon
      points={`${cx},${cy - s} ${cx + s},${cy} ${cx},${cy + s} ${cx - s},${cy}`}
      fill="#00ff88"
      stroke="var(--reef-card)"
      strokeWidth={1.5}
    />
  )
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: { value: number; payload: { timestamp: string; event: string } }[] }) {
  if (!active || !payload?.length) return null
  const { value, payload: p } = payload[0]
  const d = new Date(p.timestamp)
  return (
    <div className="bg-reef-card border border-reef-border rounded-lg px-3 py-2 text-xs shadow-lg">
      <div className="text-slate-400 font-sans">
        {d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
        {' '}
        {d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
      </div>
      <div className="text-white font-bold font-mono text-sm">
        ${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
      </div>
      {p.event && !['eod', 'daily', 'reset'].includes(p.event) && (
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

  const data = getSlice(snapshots, ts)
    .map(s => ({ timestamp: s.timestamp, portfolio_value: s.portfolio_value, event: s.event }))

  const ticks = computeTicks(data.map(d => d.timestamp), 6)
  const buyMarkers = data.filter(d => d.event === 'BUY')
  const lastPoint = data[data.length - 1]

  return (
    <div className="card p-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Portfolio Growth
        </div>
        <select
          value={ts}
          onChange={e => setTs(e.target.value as Timescale)}
          style={{
            background: 'var(--reef-elevated)',
            border: '1px solid var(--reef-border)',
            borderRadius: '4px',
            color: '#94a3b8',
            fontSize: '11px',
            fontFamily: FONT_SANS,
            fontWeight: 600,
            padding: '3px 24px 3px 10px',
            cursor: 'pointer',
            outline: 'none',
            appearance: 'none',
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2364748b'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 7px center',
            backgroundSize: '8px',
          }}
        >
          {TIMESCALES.map(t => (
            <option key={t} value={t} style={{ background: '#1a2535' }}>{t}</option>
          ))}
        </select>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
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
          <Line
            type="monotone"
            dataKey="portfolio_value"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#3b82f6' }}
            isAnimationActive={false}
          />
          {buyMarkers.map((m, i) => (
            <ReferenceDot
              key={i}
              x={m.timestamp}
              y={m.portfolio_value}
              r={6}
              shape={(props: { cx?: number; cy?: number }) => <DiamondShape cx={props.cx} cy={props.cy} />}
            />
          ))}
          {lastPoint && (
            <ReferenceDot
              x={lastPoint.timestamp}
              y={lastPoint.portfolio_value}
              r={5}
              fill="#3b82f6"
              stroke="#1e3a8a"
              strokeWidth={2}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
