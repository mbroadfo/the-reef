import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchPortfolio, fetchSharks, fetchTrades } from '../api'
import type { Portfolio, Shark, Trade } from '../types'
import MetricCard from '../components/MetricCard'
import PortfolioChart from '../components/PortfolioChart'
import SharkLeaderboard from '../components/SharkLeaderboard'
import TradesTable from '../components/TradesTable'

export default function DashboardPage({ onLive }: { onLive: (v: boolean) => void }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [sharks, setSharks]       = useState<Shark[]>([])
  const [trades, setTrades]       = useState<Trade[]>([])
  const [error, setError]         = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchPortfolio(), fetchSharks(), fetchTrades(8)])
      .then(([p, s, t]) => {
        setPortfolio(p)
        setSharks(s)
        setTrades(t.trades)
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

  const pnlPos  = portfolio.total_pnl >= 0
  const pnlSign = pnlPos ? '+' : ''

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

      {/* Metrics row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Portfolio Value"
          value={`$${portfolio.value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          sub={`Started $${portfolio.starting_cash.toLocaleString()}`}
        />
        <MetricCard
          label="Total P&L"
          value={`${pnlSign}$${Math.abs(portfolio.total_pnl).toFixed(2)}`}
          sub={`${pnlSign}${portfolio.total_pnl_pct.toFixed(2)}%`}
          positive={pnlPos}
          negative={!pnlPos}
        />
        <MetricCard
          label="Cash Available"
          value={`$${portfolio.cash.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          sub={`${((portfolio.cash / portfolio.value) * 100).toFixed(0)}% of portfolio`}
        />
        <MetricCard
          label="Win Rate"
          value={`${portfolio.win_rate_pct.toFixed(0)}%`}
          sub={`${portfolio.wins}W / ${portfolio.losses}L · PF ${portfolio.profit_factor ?? '—'}`}
          positive={portfolio.win_rate_pct >= 50}
          negative={portfolio.win_rate_pct > 0 && portfolio.win_rate_pct < 50}
        />
      </div>

      {/* Chart */}
      <PortfolioChart snapshots={portfolio.snapshots} startingCash={portfolio.starting_cash} />

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-slate-500 text-xs font-sans uppercase tracking-widest">
              Shark Performance
            </h2>
            <Link to="/sharks" className="text-slate-600 hover:text-reef-gain text-xs font-sans transition-colors">
              View all →
            </Link>
          </div>
          <SharkLeaderboard sharks={sharks} compact />
        </div>

        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-slate-500 text-xs font-sans uppercase tracking-widest">
              Recent Trades
            </h2>
            <Link to="/trades" className="text-slate-600 hover:text-reef-gain text-xs font-sans transition-colors">
              View all →
            </Link>
          </div>
          <TradesTable trades={trades} compact />
        </div>
      </div>

    </div>
  )
}
