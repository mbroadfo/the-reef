import { useNavigate, Link } from 'react-router-dom'
import type { Shark } from '../types'
import { getSharkColor, getSharkFilter, normalizeSharkName, AQUARIUM_ROSTER } from '../utils/sharks'
import sharkImg from '../assets/shark-base.png'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

export default function SharkAquarium({ sharks }: { sharks: Shark[] }) {
  const navigate = useNavigate()

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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: '8px' }}>
        {AQUARIUM_ROSTER.map((rosterName) => {
          const shark      = sharks.find((s) => s.name === rosterName)
          const isActive   = Boolean(shark) && (shark!.trades > 0)
          const color      = getSharkColor(rosterName)
          const filter     = getSharkFilter(rosterName)
          const confidence = shark?.win_rate ?? 0
          const returnVal  = isActive
            ? parseFloat(((shark!.total_pnl / 10000) * 100).toFixed(1))
            : null

          const parts     = normalizeSharkName(rosterName).split(' ')
          const firstName = parts[0]
          const lastName  = parts.slice(1).join(' ')

          return (
            <div
              key={rosterName}
              onClick={() => navigate('/sharks')}
              className={`card cursor-pointer hover:shadow-card-glow transition-all duration-200 flex flex-col items-center${!isActive ? ' opacity-50' : ''}`}
              style={{
                padding: '8px 6px 10px',
                minHeight: '220px',
                maxWidth: '120px',
                width: '100%',
                margin: '0 auto',
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
                height: '100px',
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

              {/* Return % */}
              <div style={{ textAlign: 'center', marginTop: '6px' }}>
                <div style={{
                  fontSize: '16px',
                  fontWeight: '800',
                  fontFamily: FONT_MONO,
                  color: returnVal == null ? '#64748b' : returnVal > 0 ? 'var(--reef-gain)' : returnVal < 0 ? 'var(--reef-loss)' : '#64748b',
                  lineHeight: 1,
                }}>
                  {returnVal != null ? `${returnVal > 0 ? '+' : ''}${returnVal.toFixed(1)}%` : '—'}
                </div>
                <div style={{
                  fontSize: '9px',
                  fontFamily: FONT_SANS,
                  color: '#94a3b8',
                  marginTop: '2px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}>
                  30D Return
                </div>
              </div>

              {/* Confidence bar */}
              <div style={{ width: '100%', marginTop: '8px' }}>
                <div style={{
                  width: '100%',
                  height: '4px',
                  background: 'var(--reef-border)',
                  borderRadius: '2px',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${confidence}%`,
                    height: '100%',
                    background: color,
                    borderRadius: '2px',
                    transition: 'width 300ms ease',
                  }} />
                </div>
                <div style={{
                  fontSize: '10px',
                  fontWeight: '600',
                  fontFamily: FONT_SANS,
                  color: '#94a3b8',
                  textAlign: 'center',
                  marginTop: '4px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}>
                  {confidence.toFixed(0)}% Confidence
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
