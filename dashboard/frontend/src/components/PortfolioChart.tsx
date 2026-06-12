import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import type { Snapshot } from '../types'

interface Props {
  snapshots: Snapshot[]
  startingCash: number
}

function fmt(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
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
  return (
    <div className="bg-reef-card border border-reef-border rounded-lg px-3 py-2 text-xs">
      <div className="text-slate-400 font-sans">{fmt(p.timestamp)}</div>
      <div className="text-white font-bold font-mono">${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
      {p.event && p.event !== 'daily' && (
        <div className="text-blue-400 font-sans uppercase">{p.event}</div>
      )}
    </div>
  )
}

export default function PortfolioChart({ snapshots, startingCash }: Props) {
  if (snapshots.length < 2) {
    return (
      <div className="card flex items-center justify-center h-48 text-slate-500 text-sm font-sans">
        Chart populates after first trade
      </div>
    )
  }

  const data = snapshots.map((s) => ({
    timestamp: s.timestamp,
    portfolio_value: s.portfolio_value,
    event: s.event,
  }))

  return (
    <div className="card p-4">
      <div className="text-slate-500 text-xs font-sans uppercase tracking-widest mb-4">Portfolio Value</div>
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
            tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'Space Grotesk' }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
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
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
