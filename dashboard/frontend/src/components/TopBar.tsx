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

function WinRateRing({ pct }: { pct: number }) {
  const size = 48
  const cx = size / 2
  const r = 18
  const circumference = 2 * Math.PI * r
  const filled = circumference * (pct / 100)
  const gap = 2.5
  const segments = 10
  const segArc = circumference / segments
  const segFill = segArc - gap
  const filledSegs = Math.round((pct / 100) * segments)

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {Array.from({ length: segments }).map((_, i) => {
        const offset = circumference - i * segArc
        const isOn = i < filledSegs
        return (
          <circle
            key={i}
            cx={cx} cy={cx} r={r}
            fill="none"
            stroke={isOn ? 'var(--reef-gain)' : 'var(--reef-border)'}
            strokeWidth="5"
            strokeDasharray={`${segFill} ${circumference - segFill}`}
            strokeDashoffset={offset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${cx} ${cx})`}
          />
        )
      })}
      <text x={cx} y={cx + 1} textAnchor="middle" dominantBaseline="middle"
        fill="white" fontSize="9" fontFamily="JetBrains Mono" fontWeight="700">
        {pct.toFixed(0)}%
      </text>
    </svg>
  )
}

export default function TopBar({ onMenuClick }: { onMenuClick?: () => void }) {
  const [now, setNow] = useState(() => new Date())
  const portfolio = usePortfolio()

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const sign = (n: number) => n >= 0 ? '+' : ''
  const winRate = portfolio?.win_rate_pct ?? 0
  const activeSharks = portfolio?.active_sharks ?? 0

  return (
    <div
      style={{
        height: '88px',
        display: 'flex',
        alignItems: 'center',
        borderBottom: '1px solid var(--reef-border)',
        background: 'var(--reef-card)',
        overflow: 'hidden',
      }}
    >
      {/* Hamburger — mobile only */}
      {onMenuClick && (
        <button
          onClick={onMenuClick}
          className="lg:hidden flex items-center justify-center ml-3 mr-1 shrink-0"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#94a3b8', padding: '8px', borderRadius: '6px',
            minWidth: '44px', minHeight: '44px',
          }}
          aria-label="Open navigation"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M2 5h16M2 10h16M2 15h16" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
          </svg>
        </button>
      )}

      {/* Stat pills — center column */}
      <div style={{ display: 'flex', alignItems: 'stretch', height: '100%', flex: 1, overflowX: 'auto', scrollbarWidth: 'none' }}>
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
        {/* Win Rate with segmented ring */}
        <div style={{
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
          padding: '0 20px', borderRight: '1px solid var(--reef-border)',
          minWidth: '130px', flex: '1 0 130px', height: '100%',
        }}>
          <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '4px' }}>
            Win Rate
          </div>
          <WinRateRing pct={winRate} />
        </div>
      </div>

      {/* Right rail column: Active Sharks + Market Open + Avatar */}
      <div className="hidden lg:flex" style={{
        width: '605px',
        minWidth: '605px',
        padding: '0 16px',
        alignItems: 'center',
        gap: '12px',
        borderLeft: '1px solid var(--reef-border)',
        height: '100%',
      }}>
        {/* Active Sharks */}
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', marginRight: '4px' }}>
          <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '3px' }}>
            Active Sharks
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '20px', fontWeight: 700, fontFamily: FONT_MONO, color: '#f1f5f9', lineHeight: 1 }}>
              {activeSharks}
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              <span style={{ fontSize: '10px', color: 'var(--reef-gain)', fontFamily: FONT_SANS }}>All Systems Go</span>
              <svg width="40" height="14" viewBox="0 0 40 14">
                <polyline points="0,7 8,7 11,2 14,12 17,7 25,7 28,3 31,11 34,7 40,7"
                  fill="none" stroke="var(--reef-gain)" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Market Open */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '6px 12px', borderRadius: '999px',
          background: 'var(--reef-elevated)', border: '1px solid var(--reef-border)',
        }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--reef-gain)', animation: 'pulse 2s infinite' }} />
          <span style={{ fontSize: '14px', fontFamily: FONT_SANS, color: 'white' }}>Market Open</span>
          <span style={{ fontFamily: FONT_MONO, fontSize: '13px', color: '#94a3b8' }}>{formatTime(now)}</span>
          <span style={{ fontFamily: FONT_SANS, fontSize: '12px', color: '#64748b' }}>{formatDate(now)}</span>
        </div>

        {/* User avatar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
          <div style={{
            width: '40px', height: '40px', borderRadius: '50%',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            border: '2px solid var(--reef-gain)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '15px', fontWeight: '700', fontFamily: FONT_SANS, color: 'white', flexShrink: 0,
          }}>M</div>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ color: '#64748b' }}>
            <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      </div>
    </div>
  )
}
