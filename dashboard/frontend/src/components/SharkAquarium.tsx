import { useNavigate, Link } from 'react-router-dom'
import type { Shark } from '../types'
import ConvictionBar from './ConvictionBar'
import { getSharkColor, getSharkFilter, AQUARIUM_ROSTER } from '../utils/sharks'
import sharkImg from '../assets/shark-base.png'

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

      <div className="grid grid-cols-4 xl:grid-cols-7 gap-3">
        {AQUARIUM_ROSTER.map((rosterName) => {
          const shark    = sharks.find((s) => s.name === rosterName)
          const color    = getSharkColor(rosterName)
          const filter   = getSharkFilter(rosterName)
          const isActive = Boolean(shark)
          const pnl      = shark?.total_pnl ?? null
          const pnlPct   = pnl != null ? (pnl / 10000) * 100 : null
          const winRate  = shark?.win_rate ?? 0

          return (
            <div
              key={rosterName}
              onClick={() => navigate('/sharks')}
              className={`card p-3 flex flex-col items-center gap-2 cursor-pointer hover:shadow-card-glow transition-all duration-200 relative${!isActive ? ' opacity-50' : ''}`}
            >
              {/* Name */}
              <div
                className="text-xs font-sans font-semibold text-center leading-tight"
                style={{ color }}
              >
                {rosterName}
              </div>

              {/* Illustration */}
              <div className="relative mx-auto" style={{ width: '96px', height: '96px' }}>
                <div
                  style={{
                    position: 'absolute',
                    inset: '-8px',
                    borderRadius: '50%',
                    background: color,
                    opacity: 0.25,
                    filter: 'blur(16px)',
                    zIndex: 0,
                  }}
                />
                <img
                  src={sharkImg}
                  alt={rosterName}
                  style={{
                    filter,
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    position: 'relative',
                    zIndex: 1,
                  }}
                  onError={(e) => {
                    e.currentTarget.style.display = 'none'
                    const next = e.currentTarget.nextElementSibling as HTMLElement | null
                    if (next) next.style.display = 'flex'
                  }}
                />
                {/* Fallback letter avatar */}
                <div
                  style={{ display: 'none', color }}
                  className="w-full h-full rounded-full bg-reef-elevated items-center justify-center text-2xl font-bold"
                >
                  {rosterName.charAt(0)}
                </div>
              </div>

              {/* Return % */}
              <div className="text-center">
                <div className={`text-sm font-mono font-bold ${
                  pnlPct == null
                    ? 'text-slate-500'
                    : pnlPct >= 0 ? 'text-gain' : 'text-loss'
                }`}>
                  {pnlPct == null
                    ? '—'
                    : `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`
                  }
                </div>
                <div className="text-xs font-sans text-slate-500">30D Return</div>
              </div>

              {/* Confidence bar */}
              <div className="w-full space-y-1">
                <ConvictionBar value={winRate} max={100} color={color} />
                <div className="text-xs font-sans text-slate-500 text-center">
                  {winRate.toFixed(0)}% Confidence
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
