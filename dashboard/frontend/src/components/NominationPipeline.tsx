import { useEffect, useState } from 'react'
import { fetchNominations } from '../api'
import type { Nomination } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

function TTLChip({ hours }: { hours: number }) {
  const color = hours < 6 ? '#f59e0b' : hours < 12 ? '#94a3b8' : '#475569'
  const label = hours < 1
    ? `${Math.round(hours * 60)}m left`
    : `${Math.round(hours)}h left`
  return (
    <span style={{
      fontSize: '10px', fontFamily: FONT_MONO, fontWeight: 600, color,
      border: `1px solid ${color}40`, background: `${color}12`,
      borderRadius: '4px', padding: '1px 6px', whiteSpace: 'nowrap', flexShrink: 0,
    }}>
      {label}
    </span>
  )
}

function SharkPill({ source }: { source: string }) {
  return (
    <span style={{
      fontSize: '9px', fontFamily: FONT_SANS, fontWeight: 700, color: '#3b82f6',
      textTransform: 'uppercase', letterSpacing: '0.05em',
      background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.25)',
      borderRadius: '4px', padding: '1px 6px', whiteSpace: 'nowrap', flexShrink: 0,
    }}>
      {source}
    </span>
  )
}

export default function NominationPipeline() {
  const [nominations, setNominations] = useState<Nomination[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetchNominations().then(n => { setNominations(n); setLoaded(true) }).catch(() => setLoaded(true))
    const id = setInterval(() => {
      fetchNominations().then(setNominations).catch(() => {})
    }, 120_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="card p-4 flex flex-col h-full">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <span style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Nomination Pipeline
        </span>
        <span style={{ fontSize: '10px', fontFamily: FONT_MONO, color: '#475569' }}>
          {nominations.length} active
        </span>
      </div>

      {!loaded ? (
        <div style={{ fontSize: '12px', color: '#475569', fontFamily: FONT_SANS, padding: '16px 0', textAlign: 'center' }}>Loading…</div>
      ) : nominations.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '24px 0' }}>
          <div style={{ fontSize: '24px' }}>🦈</div>
          <div style={{ fontSize: '12px', fontFamily: FONT_SANS, color: '#475569', textAlign: 'center', lineHeight: 1.5 }}>
            Scanner is hunting…<br />
            <span style={{ color: '#334155', fontSize: '11px' }}>Next cycle will surface nominations</span>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {nominations.map((n, i) => (
            <div
              key={i}
              style={{
                display: 'flex', gap: '10px', alignItems: 'flex-start',
                padding: '10px 0',
                borderBottom: i < nominations.length - 1 ? '1px solid var(--reef-border)' : 'none',
              }}
            >
              {/* Ticker badge */}
              <div style={{
                minWidth: '48px', padding: '3px 0', borderRadius: '4px', textAlign: 'center',
                fontSize: '11px', fontFamily: FONT_MONO, fontWeight: 800, color: '#f1f5f9',
                background: 'var(--reef-elevated)', border: '1px solid var(--reef-border)',
                flexShrink: 0,
              }}>
                {n.ticker}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '4px', flexWrap: 'wrap' }}>
                  <SharkPill source={n.source} />
                  {n.entry_range && (
                    <span style={{ fontSize: '10px', fontFamily: FONT_MONO, color: '#64748b' }}>
                      {n.entry_range}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#94a3b8', lineHeight: 1.5 }}>
                  {n.thesis.slice(0, 120)}{n.thesis.length > 120 ? '…' : ''}
                </div>
              </div>

              <TTLChip hours={n.expires_in_hours} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
