import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
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
    <div className="bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-xs">
      <div className="text-zinc-400">{fmt(p.timestamp)}</div>
      <div className="text-zinc-100 font-bold">${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
      {p.event && p.event !== 'daily' && (
        <div className="text-blue-400 uppercase">{p.event}</div>
      )}
    </div>
  )
}

export default function PortfolioChart({ snapshots, startingCash }: Props) {
  if (snapshots.length < 2) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg flex items-center justify-center h-48 text-zinc-600 text-sm">
        Chart populates after first trade
      </div>
    )
  }

  const data = snapshots.map((s) => ({
    timestamp: s.timestamp,
    portfolio_value: s.portfolio_value,
    event: s.event,
  }))

  const min = Math.min(...data.map((d) => d.portfolio_value))
  const max = Math.max(...data.map((d) => d.portfolio_value))
  const padding = (max - min) * 0.1 || 200
  const yMin = Math.floor((Math.min(min, startingCash) - padding) / 100) * 100
  const yMax = Math.ceil((max + padding) / 100) * 100

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="text-zinc-500 text-xs uppercase tracking-wider mb-4">Portfolio Value</div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            tick={{ fill: '#52525b', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={fmtY}
            tick={{ fill: '#52525b', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            domain={[yMin, yMax]}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="portfolio_value"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#blueGrad)"
            dot={false}
            activeDot={{ r: 4, fill: '#3b82f6' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
