import { useEffect, useState } from 'react'
import { usePortfolio } from '../context/PortfolioContext'
import { newestSnapshotMs } from '../utils/snapshots'

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

  const newest = newestSnapshotMs(portfolio?.snapshots)
  const known = newest !== null
  const lastMs = newest ?? NaN
  const ageMs = known ? now - lastMs : 0
  const stale = known && ageMs > STALE_AFTER_HOURS * 3_600_000

  const asOf = known
    ? new Date(lastMs).toLocaleString('en-US', {
        timeZone: 'America/New_York',
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
      }) + ' ET'
    : null

  const label = !known
    ? 'Portfolio snapshot time unknown'
    : `${stale ? 'STALE DATA: ' : ''}Portfolio snapshot as of ${asOf} (${formatAge(ageMs)})`

  return (
    <div
      role="status"
      style={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 14px',
        padding: '6px 16px',
        // Opaque base so contrast does not depend on what is behind the banner.
        background: `linear-gradient(${stale || !known ? 'rgba(239,68,68,0.18)' : 'rgba(245,158,11,0.14)'}, ${stale || !known ? 'rgba(239,68,68,0.18)' : 'rgba(245,158,11,0.14)'}), var(--reef-bg)`,
        borderBottom: `1px solid ${stale || !known ? 'rgba(239,68,68,0.5)' : 'rgba(245,158,11,0.45)'}`,
        fontFamily: FONT_SANS, fontSize: '12px', color: '#e2e8f0', lineHeight: 1.35,
      }}
    >
      <span style={{ fontWeight: 800, letterSpacing: '0.12em', color: '#fbbf24', whiteSpace: 'nowrap' }}>PAPER TRADING</span>
      <span style={{ color: '#cbd5e1' }}>Simulated. No real orders are placed.</span>
      <span
        title="Time of the newest stored portfolio snapshot. This is not a live feed: position prices can be older than the snapshot, and a position whose price source fails keeps its last stored price."
        style={{ marginLeft: 'auto', color: stale || !known ? '#fca5a5' : '#cbd5e1', fontWeight: stale || !known ? 700 : 400 }}
      >
        {label}. Security prices are not live.
      </span>
    </div>
  )
}
