import { useEffect, useState } from 'react'
import { usePortfolio } from '../context/PortfolioContext'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"

// Longest normal gap between snapshots is a long weekend (~3 days plus the evening report).
const STALE_AFTER_HOURS = 96

function formatAge(ms: number): string {
  const mins = Math.max(0, Math.floor(ms / 60_000))
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export default function PaperBanner() {
  const portfolio = usePortfolio()
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  const snapshots = portfolio?.snapshots
  const last = snapshots && snapshots.length > 0 ? snapshots[snapshots.length - 1].timestamp : null
  const lastMs = last ? new Date(last).getTime() : NaN
  const known = Number.isFinite(lastMs)
  const ageMs = known ? now - lastMs : 0
  const stale = known && ageMs > STALE_AFTER_HOURS * 3_600_000

  const asOf = known
    ? new Date(lastMs).toLocaleString('en-US', {
        timeZone: 'America/New_York',
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
      }) + ' ET'
    : null

  return (
    <div
      role="status"
      style={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 14px',
        padding: '5px 16px',
        background: stale ? 'rgba(239,68,68,0.14)' : 'rgba(245,158,11,0.12)',
        borderBottom: `1px solid ${stale ? 'rgba(239,68,68,0.45)' : 'rgba(245,158,11,0.4)'}`,
        fontFamily: FONT_SANS, fontSize: '12px', color: '#e2e8f0',
      }}
    >
      <span style={{ fontWeight: 800, letterSpacing: '0.12em', color: '#f59e0b' }}>PAPER TRADING</span>
      <span style={{ color: '#cbd5e1' }}>Simulated. No real orders are placed.</span>
      <span
        title="Time of the latest stored portfolio snapshot. Individual position prices can be older, and a position whose price source fails keeps its last stored price."
        style={{ marginLeft: 'auto', color: stale ? '#fca5a5' : '#cbd5e1', fontWeight: stale ? 700 : 400 }}
      >
        {known
          ? `${stale ? 'STALE DATA — ' : ''}Last snapshot ${asOf} (${formatAge(ageMs)})`
          : 'Data time unknown'}
      </span>
    </div>
  )
}
