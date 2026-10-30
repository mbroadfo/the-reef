import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import type { Shark, ConvictionData } from '../types'
import { getSharkColor, getSharkFilter, normalizeSharkName, AQUARIUM_ROSTER } from '../utils/sharks'
import { fetchConviction } from '../api'
import sharkImg from '../assets/shark-base.png'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

export default function SharkAquarium({ sharks }: { sharks: Shark[] }) {
  const navigate = useNavigate()
  const [conviction, setConviction] = useState<ConvictionData | null>(null)

  useEffect(() => {
    fetchConviction().then(setConviction).catch(() => {})
    const id = setInterval(() => fetchConviction().then(setConviction).catch(() => {}), 300_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-sans uppercase tracking-widest text-slate-500">
          Shark Aquarium
        </span>
        <Link
          to="/sharks"
          className="text-xs font-sans text-slate-500 hover:text-reef-gain transition-colors"
        >
          View All Sharks
        </Link>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '6px' }}>
        {AQUARIUM_ROSTER.map((rosterName) => {
          const shark      = sharks.find((s) => s.name === rosterName)
          const isActive   = Boolean(shark) && (shark!.trades > 0)
          const color      = getSharkColor(rosterName)
          const filter     = getSharkFilter(rosterName)
          const confidence = shark?.win_rate ?? 0
          // Reef 1.0 attributes P&L to sharks imperfectly, and sharks have no sleeve of their own,
          // so there is no honest per-shark return percentage. Show attributed dollars only.
          const pnl        = isActive ? shark!.total_pnl : null

          const parts       = normalizeSharkName(rosterName).split(' ')
          const firstName   = parts[0]
          const lastName    = parts.slice(1).join(' ')
          const convShark   = conviction?.sharks.find(s => s.shark_id === rosterName)
          const ptsLeft     = convShark?.points_remaining ?? 10
          const lastBid     = convShark?.last_bid ?? null

          return (
            <div
              key={rosterName}
              onClick={() => navigate('/sharks')}
              className={`card cursor-pointer hover:shadow-card-glow transition-all duration-200 flex flex-col items-center${!isActive ? ' opacity-60' : ''}`}
              style={{
                padding: '10px 8px 12px',
                minHeight: isActive ? '200px' : '160px',
                position: 'relative',
                borderColor: isActive ? color : undefined,
                borderWidth: isActive ? '1.5px' : undefined,
              }}
            >
              {/* Name */}
              <div style={{ textAlign: 'center', marginBottom: '6px', lineHeight: 1.2 }}>
                <div style={{ fontSize: '13px', fontWeight: '800', fontFamily: FONT_SANS, color, letterSpacing: '0.02em' }}>
                  {firstName}
                </div>
                <div style={{ fontSize: '11px', fontWeight: '700', fontFamily: FONT_SANS, color }}>
                  {lastName}
                </div>
              </div>

              {/* Illustration */}
              <div style={{
                position: 'relative',
                width: '100%',
                height: '120px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '4px 0',
                flex: 1,
              }}>
                <div style={{
                  position: 'absolute',
                  inset: '-4px',
                  borderRadius: '50%',
                  background: color,
                  opacity: 0.2,
                  filter: 'blur(18px)',
                  zIndex: 0,
                }} />
                <img
                  src={sharkImg}
                  alt={rosterName}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    objectPosition: 'center',
                    filter,
                    position: 'relative',
                    zIndex: 1,
                    mixBlendMode: 'screen',
                  }}
                />
              </div>

              {/* Attributed P&L or Hunting state */}
              {isActive ? (
                <>
                  <div style={{ textAlign: 'center', marginTop: '6px' }}>
                    <div
                      title="Reef 1.0 attribution of realized and open P&L to this shark. Not a strategy return: sharks do not yet have independent capital."
                      style={{
                        fontSize: '17px', fontWeight: '800', fontFamily: FONT_MONO,
                        color: pnl! > 0 ? 'var(--reef-gain)' : pnl! < 0 ? 'var(--reef-loss)' : '#94a3b8',
                        lineHeight: 1,
                      }}
                    >
                      {pnl! > 0 ? '+' : pnl! < 0 ? '-' : ''}${Math.abs(pnl!).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                    </div>
                    <div style={{ fontSize: '9px', fontFamily: FONT_SANS, color: '#94a3b8', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      Attributed P&amp;L
                    </div>
                  </div>
                  <div style={{ width: '100%', marginTop: '8px' }}>
                    <div style={{ width: '100%', height: '4px', background: 'var(--reef-border)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ width: `${confidence}%`, height: '100%', background: color, borderRadius: '2px', transition: 'width 300ms ease' }} />
                    </div>
                    <div style={{ fontSize: '10px', fontWeight: '600', fontFamily: FONT_SANS, color: '#94a3b8', textAlign: 'center', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      {confidence.toFixed(0)}% Win · {shark!.trades} {shark!.trades === 1 ? 'trade' : 'trades'}
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ textAlign: 'center', marginTop: '10px', padding: '6px 0' }}>
                  <div style={{ fontSize: '11px', fontFamily: FONT_SANS, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                    Hunting
                  </div>
                </div>
              )}

              {/* Conviction points */}
              <div style={{ marginTop: '8px', borderTop: '1px solid #1e293b', paddingTop: '6px', width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '9px', fontFamily: FONT_SANS, color: ptsLeft > 5 ? '#22c55e' : ptsLeft > 2 ? '#f59e0b' : '#ef4444', fontWeight: 700 }}>
                    {ptsLeft} pts
                  </span>
                  {lastBid && (
                    <span style={{ fontSize: '9px', fontFamily: FONT_MONO, fontWeight: 700, color: lastBid.bid >= 0 ? '#22c55e' : '#ef4444' }}>
                      {lastBid.ticker} {lastBid.bid >= 0 ? '+' : ''}{lastBid.bid}
                    </span>
                  )}
                </div>
                <div style={{ width: '100%', height: '3px', background: '#1e293b', borderRadius: '2px', marginTop: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${ptsLeft * 10}%`, height: '100%', background: ptsLeft > 5 ? '#22c55e' : ptsLeft > 2 ? '#f59e0b' : '#ef4444', borderRadius: '2px', transition: 'width 300ms ease' }} />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
