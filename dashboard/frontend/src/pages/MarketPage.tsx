import { useEffect, useState } from 'react'
import { fetchSectors, fetchMarket, fetchDecisions } from '../api'
import type { Sector, MarketData, Decision } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

// ── Heat cell ────────────────────────────────────────────────────────────────

function heatBg(pct: number) {
  const intensity = Math.min(Math.abs(pct) / 3, 1)
  if (pct > 0) return `rgba(0,255,136,${0.07 + intensity * 0.22})`
  if (pct < 0) return `rgba(239,68,68,${0.08 + intensity * 0.20})`
  return 'rgba(100,116,139,0.1)'
}

function HeatCell({ label, subLabel, pct, large = false }: { label: string; subLabel?: string; pct: number; large?: boolean }) {
  const color = pct >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)'
  return (
    <div style={{
      background: heatBg(pct),
      borderRadius: '8px',
      padding: large ? '14px 12px' : '10px 10px',
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      minHeight: large ? '72px' : '56px',
    }}>
      <div style={{ fontSize: '10px', fontFamily: FONT_SANS, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8' }}>
        {label}
      </div>
      {subLabel && (
        <div style={{ fontSize: '9px', fontFamily: FONT_SANS, color: '#64748b' }}>{subLabel}</div>
      )}
      <div style={{ fontSize: large ? '16px' : '14px', fontFamily: FONT_MONO, fontWeight: 700, color }}>
        {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
      </div>
    </div>
  )
}

// ── VIX gauge ────────────────────────────────────────────────────────────────

function VIXGauge({ vix }: { vix: MarketData['vix'] }) {
  const regime =
    vix.current === 0 ? 'No Data' :
    vix.current < 15 ? 'Low Vol' :
    vix.current < 20 ? 'Normal' :
    vix.current < 30 ? 'Elevated' : 'Fear'

  const regimeColor =
    vix.current === 0 ? '#64748b' :
    vix.current < 15 ? 'var(--reef-gain)' :
    vix.current < 20 ? '#f1f5f9' :
    vix.current < 30 ? '#f59e0b' : 'var(--reef-loss)'

  const pctColor = vix.pct_change >= 0 ? 'var(--reef-loss)' : 'var(--reef-gain)'

  return (
    <div className="card p-4" style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
      <div>
        <div style={{ fontSize: '10px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '4px' }}>
          VIX — Volatility Index
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
          <span style={{ fontSize: '36px', fontWeight: 800, fontFamily: FONT_MONO, color: regimeColor, lineHeight: 1 }}>
            {vix.current > 0 ? vix.current.toFixed(2) : '—'}
          </span>
          {vix.current > 0 && (
            <span style={{ fontSize: '14px', fontFamily: FONT_MONO, fontWeight: 600, color: pctColor }}>
              {vix.pct_change >= 0 ? '+' : ''}{vix.pct_change.toFixed(2)}%
            </span>
          )}
        </div>
      </div>
      <div style={{
        padding: '6px 14px', borderRadius: '6px', fontFamily: FONT_SANS, fontSize: '13px', fontWeight: 700,
        color: regimeColor, border: `1px solid ${regimeColor}30`, background: `${regimeColor}12`,
      }}>
        {regime}
      </div>
      <div style={{ marginLeft: 'auto', fontSize: '11px', fontFamily: FONT_SANS, color: '#64748b', lineHeight: 1.6 }}>
        <div>&lt;15 Low Volatility</div>
        <div>15–20 Normal</div>
        <div>20–30 Elevated</div>
        <div>&gt;30 Fear</div>
      </div>
    </div>
  )
}

// ── Signals feed ─────────────────────────────────────────────────────────────

function relTime(ts: string): string {
  const mins = Math.floor((Date.now() - new Date(ts).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function SignalsFeed({ decisions }: { decisions: Decision[] }) {
  return (
    <div className="card p-4">
      <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '12px' }}>
        Recent Signals
      </div>
      {decisions.length === 0 ? (
        <div style={{ fontSize: '12px', color: '#64748b', fontFamily: FONT_SANS, padding: '16px 0', textAlign: 'center' }}>No signals yet</div>
      ) : (
        <div>
          {decisions.map((d, i) => {
            const isBuy = d.decision === 'BUY'
            const isSell = d.decision === 'SELL'
            const badgeColor = isBuy ? { bg: 'rgba(59,130,246,0.12)', text: '#3b82f6', border: 'rgba(59,130,246,0.3)' }
                             : isSell ? { bg: 'rgba(245,158,11,0.12)', text: '#f59e0b', border: 'rgba(245,158,11,0.3)' }
                             : { bg: 'rgba(100,116,139,0.12)', text: '#64748b', border: 'rgba(100,116,139,0.3)' }
            return (
              <div
                key={i}
                style={{
                  display: 'flex', gap: '10px', alignItems: 'flex-start',
                  padding: '10px 0', borderBottom: i < decisions.length - 1 ? '1px solid var(--reef-border)' : 'none',
                }}
              >
                {/* Decision badge */}
                <div style={{
                  width: '44px', padding: '2px 0', borderRadius: '4px', flexShrink: 0, textAlign: 'center',
                  fontSize: '10px', fontFamily: FONT_MONO, fontWeight: 700,
                  color: badgeColor.text, background: badgeColor.bg, border: `1px solid ${badgeColor.border}`,
                }}>
                  {d.decision || 'PASS'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '2px' }}>
                    <span style={{ fontSize: '13px', fontFamily: FONT_MONO, fontWeight: 700, color: '#f1f5f9' }}>{d.ticker}</span>
                    {d.signal_type && (
                      <span style={{ fontSize: '9px', fontFamily: FONT_SANS, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {d.signal_type}
                      </span>
                    )}
                    <span style={{ fontSize: '10px', fontFamily: FONT_MONO, color: '#3b82f6', marginLeft: 'auto' }}>
                      {d.conviction}/10
                    </span>
                  </div>
                  {d.rationale && (
                    <div style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#64748b', lineHeight: 1.5 }}>
                      {d.rationale.slice(0, 140)}{d.rationale.length > 140 ? '…' : ''}
                    </div>
                  )}
                  <div style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#475569', marginTop: '3px' }}>
                    {relTime(d.timestamp)}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  const [sectors, setSectors]     = useState<Sector[]>([])
  const [market, setMarket]       = useState<MarketData | null>(null)
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [loaded, setLoaded]       = useState(false)

  useEffect(() => {
    Promise.all([fetchSectors(), fetchMarket(), fetchDecisions()])
      .then(([s, m, d]) => { setSectors(s); setMarket(m); setDecisions(d); setLoaded(true) })
      .catch(() => setLoaded(true))
  }, [])

  if (!loaded) {
    return <div className="px-6 py-12 text-slate-500 text-sm font-sans animate-pulse">Loading...</div>
  }

  return (
    <div className="px-6 py-6 space-y-4">

      {/* VIX */}
      {market && <VIXGauge vix={market.vix} />}

      {/* Sector Heat Map */}
      <div className="card p-4">
        <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '12px' }}>
          Sector Heat Map
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
          {sectors.map(s => (
            <HeatCell key={s.ticker} label={s.sector} subLabel={s.ticker} pct={s.pct_change} large />
          ))}
        </div>
      </div>

      {/* Portfolio Holdings Heat */}
      {market && market.holdings.length > 0 && (
        <div className="card p-4">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
              Portfolio Holdings
            </div>
            <span style={{ fontSize: '10px', fontFamily: FONT_SANS, color: '#64748b' }}>Daily change</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px', marginBottom: '16px' }}>
            {market.holdings.map(h => (
              <HeatCell key={h.ticker} label={h.ticker} subLabel={`$${(h.market_value / 1000).toFixed(1)}k`} pct={h.daily_pct} />
            ))}
          </div>
          <div style={{ borderTop: '1px solid var(--reef-border)', paddingTop: '12px' }}>
            <div style={{ fontSize: '10px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b', marginBottom: '8px' }}>
              Total Return (since entry)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
              {market.holdings.map(h => (
                <HeatCell key={h.ticker} label={h.ticker} pct={h.unrealized_pnl_pct} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Signals feed */}
      <SignalsFeed decisions={decisions} />

    </div>
  )
}
