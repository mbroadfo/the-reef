import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchPortfolio, fetchSharks, fetchTrades, fetchPositions } from '../api'
import type { Portfolio, Shark, Trade, Position } from '../types'
import PortfolioChart from '../components/PortfolioChart'
import SharkAquarium from '../components/SharkAquarium'
import TradesTable from '../components/TradesTable'
import PositionsOverview from '../components/PositionsOverview'
import TradeDetails from '../components/TradeDetails'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

interface MetricBoxProps {
  label: string
  value: string
  positive?: boolean
}

function MetricBox({ label, value, positive }: MetricBoxProps) {
  const color = positive === undefined ? '#f1f5f9' : positive ? 'var(--reef-gain)' : 'var(--reef-loss)'
  return (
    <div style={{
      background: 'var(--reef-card)',
      border: '1px solid var(--reef-border)',
      borderRadius: '8px',
      padding: '10px 14px',
      flex: 1,
      minWidth: 0,
    }}>
      <div style={{ fontSize: '10px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '4px' }}>
        {label}
      </div>
      <div style={{ fontSize: '14px', fontWeight: 700, fontFamily: FONT_MONO, color }}>
        {value}
      </div>
    </div>
  )
}

export default function DashboardPage({ onLive }: { onLive: (v: boolean) => void }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [sharks, setSharks]       = useState<Shark[]>([])
  const [trades, setTrades]       = useState<Trade[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [error, setError]         = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchPortfolio(), fetchSharks(), fetchTrades(20), fetchPositions()])
      .then(([p, s, t, pos]) => {
        setPortfolio(p)
        setSharks(s)
        setTrades(t.trades)
        setPositions(pos)
        onLive(true)
      })
      .catch((e) => {
        setError(String(e))
        onLive(false)
      })
  }, [onLive])

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-loss text-sm font-sans">
        API error: {error}
      </div>
    )
  }

  if (!portfolio) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-slate-500 text-sm font-sans animate-pulse">
        Loading...
      </div>
    )
  }

  const lastSell = trades.find(t => t.action === 'SELL' && t.pnl !== null) ?? null

  return (
    <div className="px-6 py-6 space-y-4">

      {/* Chart */}
      <PortfolioChart snapshots={portfolio.snapshots} startingCash={portfolio.starting_cash} />

      {/* Sub-metrics row */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <MetricBox
          label="Starting Value"
          value={`$${fmt(portfolio.starting_cash)}`}
        />
        <MetricBox
          label="Total Return"
          value={`${portfolio.total_pnl_pct >= 0 ? '+' : ''}${portfolio.total_pnl_pct.toFixed(1)}%`}
          positive={portfolio.total_pnl_pct >= 0}
        />
        <MetricBox
          label="Profit Factor"
          value={portfolio.profit_factor != null ? portfolio.profit_factor.toFixed(2) : '—'}
          positive={portfolio.profit_factor != null ? portfolio.profit_factor >= 1 : undefined}
        />
        <MetricBox
          label="Best Trade"
          value={portfolio.max_trade_gain != null ? `+$${fmt(portfolio.max_trade_gain)}` : '—'}
          positive={true}
        />
        <MetricBox
          label="Max Drawdown"
          value={portfolio.max_drawdown != null ? `${portfolio.max_drawdown.toFixed(1)}%` : '—'}
          positive={false}
        />
      </div>

      {/* Aquarium */}
      <SharkAquarium sharks={sharks} />

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Left: Recent Trades */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-slate-500 text-xs font-sans uppercase tracking-widest">
              Recent Trades
            </h2>
            <Link to="/trades" className="text-slate-600 hover:text-reef-gain text-xs font-sans transition-colors">
              View all →
            </Link>
          </div>
          <div style={{ maxHeight: '340px', overflowY: 'auto' }}>
            <TradesTable trades={trades} dashboard />
          </div>
        </div>

        {/* Right: Positions + Trade Details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <PositionsOverview positions={positions} />
          <TradeDetails trade={lastSell} />
        </div>

      </div>
    </div>
  )
}
