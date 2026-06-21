import { useEffect, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts'
import { fetchPortfolio, fetchPositions } from '../api'
import type { Portfolio, Position, Snapshot } from '../types'
import PortfolioChart from '../components/PortfolioChart'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function fmt(n: number, digits = 2) {
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// ── Drawdown chart ────────────────────────────────────────────────────────────

type Timescale = '1W' | '1M' | '3M' | 'All'
const TIMESCALES: Timescale[] = ['1W', '1M', '3M', 'All']

function getSlice(snapshots: Snapshot[], ts: Timescale): Snapshot[] {
  if (ts === 'All' || snapshots.length === 0) return snapshots
  const now = Date.now()
  const weekCutoff = now - 7 * 86400000
  const weekCount = snapshots.filter(s => new Date(s.timestamp).getTime() >= weekCutoff).length
  if (ts === '1W') return snapshots.filter(s => new Date(s.timestamp).getTime() >= weekCutoff)
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

function computeDrawdown(snapshots: Snapshot[]): { timestamp: string; drawdown: number }[] {
  let peak = 0
  return snapshots.map(s => {
    if (s.portfolio_value > peak) peak = s.portfolio_value
    const dd = peak > 0 ? -((peak - s.portfolio_value) / peak * 100) : 0
    return { timestamp: s.timestamp, drawdown: dd }
  })
}

function DrawdownChart({ snapshots }: { snapshots: Snapshot[] }) {
  const [ts, setTs] = useState<Timescale>('All')
  const slice = getSlice(snapshots, ts)
  const data = computeDrawdown(slice)
  const ticks = computeTicks(data.map(d => d.timestamp), 6)

  return (
    <div className="card p-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Drawdown
        </div>
        <div style={{ display: 'flex', gap: '4px' }}>
          {TIMESCALES.map(t => (
            <button
              key={t}
              onClick={() => setTs(t)}
              style={{
                padding: '3px 10px', borderRadius: '4px', fontSize: '11px', fontFamily: FONT_SANS,
                fontWeight: 600, cursor: 'pointer', border: '1px solid',
                borderColor: ts === t ? '#ef4444' : 'var(--reef-border)',
                background: ts === t ? 'rgba(239,68,68,0.12)' : 'transparent',
                color: ts === t ? '#ef4444' : '#64748b',
                transition: 'all 150ms',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" vertical={false} />
          <XAxis
            dataKey="timestamp"
            ticks={ticks}
            tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'Space Grotesk' }}
            axisLine={false} tickLine={false}
          />
          <YAxis
            tickFormatter={(v) => `${v.toFixed(1)}%`}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            axisLine={false} tickLine={false}
            domain={[(dataMin: number) => Math.floor(dataMin * 1.1), 0]}
            width={52}
          />
          <Tooltip
            formatter={(v: number) => [`${v.toFixed(2)}%`, 'Drawdown']}
            labelFormatter={(l) => new Date(l).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            contentStyle={{ background: 'var(--reef-card)', border: '1px solid var(--reef-border)', borderRadius: '6px', fontSize: '11px' }}
          />
          <Area
            type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={1.5}
            fill="url(#ddGrad)" dot={false} isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Cash vs Equity donut ──────────────────────────────────────────────────────

const DONUT_COLORS = ['#00ff88', '#3b82f6']

function AllocationDonut({ cash, equity }: { cash: number; equity: number }) {
  const total = cash + equity
  const data = [
    { name: 'Equity', value: equity },
    { name: 'Cash', value: cash },
  ]
  return (
    <div className="card p-4">
      <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '10px' }}>
        Allocation
      </div>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <ResponsiveContainer width={100} height={100}>
          <PieChart>
            <Pie data={data} cx="50%" cy="50%" innerRadius={30} outerRadius={46} dataKey="value" strokeWidth={0} isAnimationActive={false}>
              {data.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i]} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div style={{ flex: 1 }}>
          {data.map((d, i) => (
            <div key={d.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: i === 0 ? '1px solid var(--reef-border)' : 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', background: DONUT_COLORS[i] }} />
                <span style={{ fontSize: '12px', fontFamily: FONT_SANS, color: '#94a3b8' }}>{d.name}</span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '12px', fontFamily: FONT_MONO, color: '#f1f5f9', fontWeight: 600 }}>
                  ${fmt(d.value, 0)}
                </div>
                <div style={{ fontSize: '10px', fontFamily: FONT_MONO, color: '#64748b' }}>
                  {total > 0 ? (d.value / total * 100).toFixed(1) : '0.0'}%
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Positions breakdown table ─────────────────────────────────────────────────

function PositionsBreakdown({ positions }: { positions: Position[] }) {
  const totalMv = positions.reduce((s, p) => s + p.market_value, 0)

  if (!positions.length) {
    return (
      <div className="card flex items-center justify-center h-32 text-slate-500 text-sm font-sans">
        No open positions
      </div>
    )
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full" style={{ fontSize: '12px' }}>
        <thead>
          <tr className="border-b border-reef-border">
            {['Ticker', 'Shares', 'Entry', 'Current', 'Cost Basis', 'Mkt Value', 'P&L', 'P&L %', 'Alloc'].map(h => (
              <th key={h} className="text-left text-slate-500 font-sans font-medium uppercase tracking-widest px-4 py-3" style={{ fontSize: '10px' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const isPos = p.unrealized_pnl >= 0
            const pnlColor = isPos ? 'var(--reef-gain)' : 'var(--reef-loss)'
            const alloc = totalMv > 0 ? (p.market_value / totalMv * 100) : 0
            return (
              <tr key={p.ticker} className="border-b border-reef-border/50 hover:bg-reef-elevated/30 transition-colors">
                <td className="px-4 py-2.5 font-bold font-mono text-blue-400">{p.ticker}</td>
                <td className="px-4 py-2.5 font-mono text-slate-300">{p.shares}</td>
                <td className="px-4 py-2.5 font-mono text-slate-400">${p.entry_price.toFixed(2)}</td>
                <td className="px-4 py-2.5 font-mono text-white font-semibold">${p.current_price.toFixed(2)}</td>
                <td className="px-4 py-2.5 font-mono text-slate-400">${fmt(p.cost_basis)}</td>
                <td className="px-4 py-2.5 font-mono text-slate-200">${fmt(p.market_value)}</td>
                <td className="px-4 py-2.5 font-mono font-semibold" style={{ color: pnlColor }}>
                  {isPos ? '+' : ''}${Math.abs(p.unrealized_pnl).toFixed(2)}
                </td>
                <td className="px-4 py-2.5 font-mono" style={{ color: pnlColor }}>
                  {isPos ? '+' : ''}{p.unrealized_pnl_pct.toFixed(1)}%
                </td>
                <td className="px-4 py-2.5">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <div style={{ width: '48px', height: '4px', background: 'var(--reef-border)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(alloc, 100)}%`, height: '100%', background: '#3b82f6', borderRadius: '2px' }} />
                    </div>
                    <span style={{ fontSize: '11px', fontFamily: FONT_MONO, color: '#64748b' }}>{alloc.toFixed(1)}%</span>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Metric pill ───────────────────────────────────────────────────────────────

function MetricPill({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const color = positive === undefined ? '#f1f5f9' : positive ? 'var(--reef-gain)' : 'var(--reef-loss)'
  return (
    <div style={{ background: 'var(--reef-card)', border: '1px solid var(--reef-border)', borderRadius: '8px', padding: '10px 14px', flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: '10px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '14px', fontWeight: 700, fontFamily: FONT_MONO, color }}>{value}</div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [positions, setPositions] = useState<Position[]>([])

  useEffect(() => {
    Promise.all([fetchPortfolio(), fetchPositions()])
      .then(([p, pos]) => { setPortfolio(p); setPositions(pos) })
      .catch(() => {})
  }, [])

  if (!portfolio) {
    return <div className="px-6 py-12 text-slate-500 text-sm font-sans animate-pulse">Loading...</div>
  }

  const totalMv = positions.reduce((s, p) => s + p.market_value, 0)
  const unrealizedTotal = positions.reduce((s, p) => s + p.unrealized_pnl, 0)

  return (
    <div className="px-6 py-6 space-y-4">

      {/* NAV Chart */}
      <PortfolioChart snapshots={portfolio.snapshots} startingCash={portfolio.starting_cash} />

      {/* Sub-metrics */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <MetricPill label="Starting Value" value={`$${fmt(portfolio.starting_cash)}`} />
        <MetricPill label="Current NAV" value={`$${fmt(portfolio.value)}`} />
        <MetricPill label="Total Return" value={`${portfolio.total_pnl_pct >= 0 ? '+' : ''}${portfolio.total_pnl_pct.toFixed(1)}%`} positive={portfolio.total_pnl_pct >= 0} />
        <MetricPill label="Realized P&L" value={`${portfolio.realized_pnl >= 0 ? '+' : ''}$${fmt(portfolio.realized_pnl)}`} positive={portfolio.realized_pnl >= 0} />
        <MetricPill label="Unrealized P&L" value={`${unrealizedTotal >= 0 ? '+' : ''}$${fmt(unrealizedTotal)}`} positive={unrealizedTotal >= 0} />
        <MetricPill label="Win Rate" value={`${portfolio.win_rate_pct.toFixed(1)}%`} positive={portfolio.win_rate_pct >= 50} />
      </div>

      {/* Cash vs Equity + Positions */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 240px', gap: '16px', alignItems: 'start' }}>
        <PositionsBreakdown positions={positions} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <AllocationDonut cash={portfolio.cash} equity={totalMv} />
          <div className="card p-4">
            <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '10px' }}>
              Risk Metrics
            </div>
            {[
              { label: 'Profit Factor', value: portfolio.profit_factor != null ? portfolio.profit_factor.toFixed(2) : '—', positive: portfolio.profit_factor != null ? portfolio.profit_factor >= 1 : undefined },
              { label: 'Max Drawdown', value: portfolio.max_drawdown != null ? `${portfolio.max_drawdown.toFixed(1)}%` : '—', positive: false },
              { label: 'Best Trade', value: portfolio.max_trade_gain != null ? `+$${fmt(portfolio.max_trade_gain)}` : '—', positive: true },
              { label: 'Trades', value: String(portfolio.total_trades), positive: undefined },
              { label: 'Cash', value: `$${fmt(portfolio.cash)}`, positive: undefined },
            ].map(({ label, value, positive }) => {
              const color = positive === undefined ? '#f1f5f9' : positive ? 'var(--reef-gain)' : 'var(--reef-loss)'
              return (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid var(--reef-border)' }}>
                  <span style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#64748b' }}>{label}</span>
                  <span style={{ fontSize: '12px', fontFamily: FONT_MONO, color, fontWeight: 600 }}>{value}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Drawdown chart */}
      {portfolio.snapshots.length >= 2 && (
        <DrawdownChart snapshots={portfolio.snapshots} />
      )}

    </div>
  )
}
