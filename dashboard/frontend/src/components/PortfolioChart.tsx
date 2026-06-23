import { useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceDot, ResponsiveContainer,
} from 'recharts'
import type { Snapshot } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

type Timescale = '1D' | '3D' | '5D' | '1W' | '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'Max'

const ALL_TIMESCALES: Timescale[] = ['1D', '3D', '5D', '1W', '1M', '3M', '6M', '1Y', '3Y', '5Y', 'Max']

const RANGE_DAYS: Record<Timescale, number | null> = {
  '1D': 1, '3D': 3, '5D': 5, '1W': 7, '1M': 30, '3M': 90,
  '6M': 180, '1Y': 365, '3Y': 1095, '5Y': 1825, 'Max': null,
}

function getSlice(snapshots: Snapshot[], ts: Timescale): Snapshot[] {
  const days = RANGE_DAYS[ts]
  if (days === null || snapshots.length === 0) return snapshots
  const cutoff = Date.now() - days * 86400000
  const filtered = snapshots.filter(s => new Date(s.timestamp).getTime() >= cutoff)
  return filtered.length > 1 ? filtered : snapshots
}

function tickFormat(ts: Timescale, v: string): string {
  const d = new Date(v)
  if (ts === '1D') return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  if (ts === '1Y' || ts === '3Y' || ts === '5Y' || ts === 'Max')
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
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
        {' '}{d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
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
  const dataDays = useMemo(() => {
    if (snapshots.length === 0) return 0
    return (Date.now() - new Date(snapshots[0].timestamp).getTime()) / 86400000
  }, [snapshots])

  const enabledSet = useMemo(() => {
    return new Set(ALL_TIMESCALES.filter(ts => {
      const days = RANGE_DAYS[ts]
      return days === null || dataDays >= days
    }))
  }, [dataDays])

  const defaultTs: Timescale = useMemo(() => {
    if (dataDays < 1) return '1D'
    if (dataDays < 3) return '3D'
    if (dataDays < 5) return '5D'
    if (dataDays < 7) return '1W'
    if (dataDays < 30) return '1W'
    return '1M'
  }, [dataDays])

  const [ts, setTs] = useState<Timescale>(defaultTs)

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
    <div className="card p-3">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Portfolio Growth
        </div>
        {/* Timescale pill buttons */}
        <div style={{ display: 'flex', gap: '2px' }}>
          {ALL_TIMESCALES.map(t => {
            const on = enabledSet.has(t)
            const active = t === ts
            return (
              <button
                key={t}
                disabled={!on}
                onClick={() => on && setTs(t)}
                style={{
                  padding: '2px 7px',
                  borderRadius: '4px',
                  border: active ? '1px solid rgba(59,130,246,0.5)' : '1px solid transparent',
                  background: active ? 'rgba(59,130,246,0.15)' : 'transparent',
                  color: active ? '#3b82f6' : on ? '#64748b' : '#2d3748',
                  fontSize: '10px',
                  fontFamily: FONT_SANS,
                  fontWeight: 600,
                  cursor: on ? 'pointer' : 'default',
                  transition: 'all 0.15s',
                }}
              >
                {t}
              </button>
            )
          })}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" vertical={false} />
          <XAxis
            dataKey="timestamp"
            ticks={ticks}
            tickFormatter={v => tickFormat(ts, v)}
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
