import { useEffect, useState } from 'react'
import { fetchSharks, fetchPositions } from '../api'
import { usePortfolio } from '../context/PortfolioContext'
import type { Shark, Position } from '../types'
import PortfolioChart from '../components/PortfolioChart'
import SharkAquarium from '../components/SharkAquarium'
import TickerTape from '../components/TickerTape'
import NominationPipeline from '../components/NominationPipeline'
import AlphaBenchmark from '../components/AlphaBenchmark'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

interface MetricBoxProps {
  label: string
  value: string
  subtitle?: string
  positive?: boolean
}

function MetricBox({ label, value, subtitle, positive }: MetricBoxProps) {
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
      {subtitle && (
        <div style={{ fontSize: '11px', fontWeight: 600, fontFamily: FONT_MONO, color, marginTop: '1px', opacity: 0.8 }}>
          {subtitle}
        </div>
      )}
    </div>
  )
}

export default function DashboardPage({ onLive }: { onLive: (v: boolean) => void }) {
  const portfolio                  = usePortfolio()
  const [sharks, setSharks]       = useState<Shark[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [error, setError]         = useState<string | null>(null)
  const [ready, setReady]         = useState(false)

  useEffect(() => {
    Promise.all([fetchSharks(), fetchPositions()])
      .then(([s, pos]) => {
        setSharks(s)
        setPositions(pos)
        setReady(true)
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

  if (!portfolio || !ready) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-slate-500 text-sm font-sans animate-pulse">
        Loading...
      </div>
    )
  }

  const bestDay = portfolio.snapshots.length > 1
    ? Math.max(...portfolio.snapshots.slice(1).map((s, i) => s.portfolio_value - portfolio.snapshots[i].portfolio_value))
    : 0

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
          label="Total Gain"
          value={`${portfolio.total_pnl >= 0 ? '+' : ''}$${fmt(portfolio.total_pnl)}`}
          subtitle={`${portfolio.total_pnl_pct >= 0 ? '+' : ''}${portfolio.total_pnl_pct.toFixed(1)}%`}
          positive={portfolio.total_pnl_pct >= 0}
        />
        <MetricBox
          label="Open Positions"
          value={`${positions.length}`}
        />
        <MetricBox
          label="Best Day"
          value={bestDay > 0 ? `+$${fmt(bestDay)}` : '—'}
          positive={bestDay > 0}
        />
        <MetricBox
          label="Max Drawdown"
          value={portfolio.max_drawdown != null ? `${portfolio.max_drawdown.toFixed(1)}%` : '—'}
          positive={false}
        />
      </div>

      {/* Aquarium */}
      <SharkAquarium sharks={sharks} />

      {/* Ticker tape */}
      <TickerTape />

      {/* Bottom row — fixed height so both cards align */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ height: '460px' }}>
        <NominationPipeline />
        <AlphaBenchmark />
      </div>

    </div>
  )
}
