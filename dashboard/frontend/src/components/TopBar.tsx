import { useState, useEffect } from 'react'
import { usePortfolio } from '../context/PortfolioContext'
import StatPill from './StatPill'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function formatTime(d: Date): string {
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: true, timeZone: 'America/New_York',
  }) + ' ET'
}

function formatDate(d: Date): string {
  return d.toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
    timeZone: 'America/New_York',
  })
}

export default function TopBar() {
  const [now, setNow] = useState(() => new Date())
  const portfolio = usePortfolio()

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const sign = (n: number) => n >= 0 ? '+' : ''

  return (
    <div
      style={{
        gridColumn: '2 / 4',
        gridRow: '1',
        height: '88px',
        display: 'flex',
        alignItems: 'center',
        borderBottom: '1px solid var(--reef-border)',
        background: 'var(--reef-card)',
        overflow: 'hidden',
      }}
    >
      {/* Stat pills */}
      <div style={{ display: 'flex', alignItems: 'stretch', height: '100%', flex: 1 }}>
        <StatPill
          label="Portfolio Value"
          value={portfolio ? `$${fmt(portfolio.value)}` : '$—'}
          sparkline={portfolio?.snapshots?.map(s => s.portfolio_value)}
          positive={(portfolio?.total_pnl ?? 0) >= 0}
        />
        <StatPill
          label="Today's Gain"
          value={portfolio?.today_gain !== undefined
            ? `${sign(portfolio.today_gain)}$${fmt(Math.abs(portfolio.today_gain))}`
            : '$—'}
          change={portfolio?.today_gain_pct !== undefined
            ? `${sign(portfolio.today_gain_pct)}${portfolio.today_gain_pct.toFixed(2)}%`
            : undefined}
          positive={(portfolio?.today_gain ?? 0) >= 0}
        />
        <StatPill
          label="This Month"
          value={portfolio?.month_gain !== undefined
            ? `${sign(portfolio.month_gain)}$${fmt(Math.abs(portfolio.month_gain))}`
            : '$—'}
          change={portfolio?.month_gain_pct !== undefined
            ? `${sign(portfolio.month_gain_pct)}${portfolio.month_gain_pct.toFixed(2)}%`
            : undefined}
          positive={(portfolio?.month_gain ?? 0) >= 0}
        />
        <StatPill
          label="Win Rate"
          value={`${(portfolio?.win_rate_pct ?? 0).toFixed(1)}%`}
        />
        <StatPill
          label="Active Sharks"
          value={String(portfolio?.active_sharks ?? 0)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginLeft: '4px' }}>
            <span style={{ fontSize: '10px', color: 'var(--reef-gain)', fontFamily: FONT_SANS }}>
              All Systems Go
            </span>
            <svg width="40" height="16" viewBox="0 0 40 16">
              <polyline
                points="0,8 8,8 11,2 14,14 17,8 25,8 28,4 31,12 34,8 40,8"
                fill="none"
                stroke="var(--reef-gain)"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        </StatPill>
      </div>

      {/* Right: clock + user avatar */}
      <div style={{
        padding: '0 16px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        borderLeft: '1px solid var(--reef-border)',
        height: '100%',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 12px',
          borderRadius: '999px',
          background: 'var(--reef-elevated)',
          border: '1px solid var(--reef-border)',
        }}>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: 'var(--reef-gain)',
            animation: 'pulse 2s infinite',
          }} />
          <span style={{ fontSize: '14px', fontFamily: FONT_SANS, color: 'white' }}>
            Market Open
          </span>
          <span style={{ fontFamily: FONT_MONO, fontSize: '13px', color: '#94a3b8' }}>
            {formatTime(now)}
          </span>
          <span style={{ fontFamily: FONT_SANS, fontSize: '12px', color: '#64748b' }}>
            {formatDate(now)}
          </span>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          cursor: 'pointer',
        }}>
          <div style={{
            width: '40px', height: '40px', borderRadius: '50%',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            border: '2px solid var(--reef-gain)',
            display: 'flex', alignItems: 'center',
            justifyContent: 'center',
            fontSize: '15px', fontWeight: '700',
            fontFamily: FONT_SANS, color: 'white',
            flexShrink: 0,
          }}>
            M
          </div>
          <svg width="12" height="12" viewBox="0 0 12 12"
               fill="none" style={{ color: '#64748b' }}>
            <path d="M2 4l4 4 4-4" stroke="currentColor"
                  strokeWidth="1.5" strokeLinecap="round"
                  strokeLinejoin="round"/>
          </svg>
        </div>
      </div>
    </div>
  )
}
