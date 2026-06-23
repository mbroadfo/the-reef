import { useEffect, useState } from 'react'
import { fetchAlpha } from '../api'
import type { AlphaData } from '../types'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

const W = 480
const H = 140

function Sparkline({ data }: { data: AlphaData }) {
  const reef = data.reef_series
  const spy  = data.spy_series

  if (reef.length < 2) {
    return (
      <div style={{
        height: `${H}px`, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '11px', fontFamily: FONT_SANS, color: '#475569',
      }}>
        Accumulating data…
      </div>
    )
  }

  const allVals = [...reef.map(p => p.value), ...spy.map(p => p.value)]
  const minV = Math.min(...allVals)
  const maxV = Math.max(...allVals)
  const range = maxV - minV || 1
  const pad = 8

  function toX(i: number, len: number) {
    return pad + (i / (len - 1)) * (W - pad * 2)
  }
  function toY(v: number) {
    return H - pad - ((v - minV) / range) * (H - pad * 2)
  }

  function polyline(series: typeof reef, color: string, opacity = 1) {
    const pts = series.map((p, i) => `${toX(i, series.length).toFixed(1)},${toY(p.value).toFixed(1)}`).join(' ')
    return <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeOpacity={opacity} strokeLinejoin="round" strokeLinecap="round" />
  }

  // Reef area fill
  const reefPts = reef.map((p, i) => `${toX(i, reef.length).toFixed(1)},${toY(p.value).toFixed(1)}`).join(' ')
  const areaPath = `M${toX(0, reef.length).toFixed(1)},${H} L${reefPts.replace(/(\d+\.?\d*),(\d+\.?\d*)/g, '$1,$2')} L${toX(reef.length - 1, reef.length).toFixed(1)},${H} Z`

  // Endpoint dot on reef
  const lastReef = reef[reef.length - 1]
  const ex = toX(reef.length - 1, reef.length)
  const ey = toY(lastReef.value)

  // Baseline (100) line
  const baseY = toY(100)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: `${H}px` }}>
      {/* Baseline at 100 */}
      <line x1={pad} y1={baseY} x2={W - pad} y2={baseY} stroke="#1e293b" strokeWidth="1" strokeDasharray="4 3" />

      {/* Reef area */}
      <path d={areaPath} fill="rgba(59,130,246,0.06)" />

      {/* SPY line */}
      {polyline(spy, '#475569', 0.7)}

      {/* Reef line */}
      {polyline(reef, '#3b82f6')}

      {/* Endpoint dot */}
      <circle cx={ex} cy={ey} r="4" fill="#3b82f6" />
      <circle cx={ex} cy={ey} r="7" fill="none" stroke="#3b82f6" strokeWidth="1" strokeOpacity="0.4" />
    </svg>
  )
}

function StatBox({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  const color = positive === undefined ? '#94a3b8' : positive ? 'var(--reef-gain)' : 'var(--reef-loss)'
  return (
    <div style={{ textAlign: 'center', flex: 1 }}>
      <div style={{ fontSize: '9px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#475569', marginBottom: '3px' }}>
        {label}
      </div>
      <div style={{ fontSize: '15px', fontWeight: 800, fontFamily: FONT_MONO, color, lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '9px', fontFamily: FONT_SANS, color: '#475569', marginTop: '2px' }}>
          {sub}
        </div>
      )}
    </div>
  )
}

export default function AlphaBenchmark() {
  const [data, setData]     = useState<AlphaData | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetchAlpha().then(d => { setData(d); setLoaded(true) }).catch(() => setLoaded(true))
  }, [])

  const alpha     = data?.alpha ?? null
  const alphaPos  = alpha !== null ? alpha >= 0 : undefined
  const alphaStr  = alpha !== null ? `${alpha >= 0 ? '+' : ''}${alpha.toFixed(2)}%` : '—'

  return (
    <div className="card p-4 flex flex-col h-full">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span style={{ fontSize: '11px', fontFamily: FONT_SANS, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
          Alpha vs Benchmark
        </span>
        <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '10px', fontFamily: FONT_SANS, color: '#3b82f6' }}>
            <span style={{ display: 'inline-block', width: '16px', height: '2px', background: '#3b82f6', borderRadius: '1px' }} />
            The Reef
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '10px', fontFamily: FONT_SANS, color: '#475569' }}>
            <span style={{ display: 'inline-block', width: '16px', height: '2px', background: '#475569', borderRadius: '1px', opacity: 0.7 }} />
            SPY
          </span>
        </div>
      </div>

      {/* Hero alpha */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '8px' }}>
        <span style={{
          fontSize: '28px', fontWeight: 900, fontFamily: FONT_MONO, lineHeight: 1,
          color: alphaPos === undefined ? '#475569' : alphaPos ? 'var(--reef-gain)' : 'var(--reef-loss)',
        }}>
          {alphaStr}
        </span>
        <span style={{ fontSize: '11px', fontFamily: FONT_SANS, color: '#475569' }}>alpha</span>
      </div>

      {/* Chart */}
      {!loaded ? (
        <div style={{ height: `${H}px`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ fontSize: '11px', color: '#475569', fontFamily: FONT_SANS }} className="animate-pulse">Loading…</div>
        </div>
      ) : data ? (
        <Sparkline data={data} />
      ) : null}

      {/* Stats row */}
      <div style={{ display: 'flex', borderTop: '1px solid var(--reef-border)', paddingTop: '12px', marginTop: '8px' }}>
        <StatBox
          label="Sharpe"
          value={data?.sharpe != null ? String(data.sharpe) : '—'}
          sub={data?.sharpe == null ? 'need 10 days' : undefined}
        />
        <div style={{ width: '1px', background: 'var(--reef-border)', margin: '0 8px' }} />
        <StatBox
          label="Win Rate"
          value={data?.win_rate != null ? `${data.win_rate}%` : '—'}
          positive={data?.win_rate != null ? data.win_rate >= 50 : undefined}
        />
        <div style={{ width: '1px', background: 'var(--reef-border)', margin: '0 8px' }} />
        <StatBox
          label="Conviction"
          value={data?.conviction_winners != null ? String(data.conviction_winners) : '—'}
          sub={data?.conviction_losers != null ? `losers ${data.conviction_losers}` : 'winners avg'}
          positive={
            data?.conviction_winners != null && data?.conviction_losers != null
              ? data.conviction_winners > data.conviction_losers
              : undefined
          }
        />
      </div>
    </div>
  )
}
