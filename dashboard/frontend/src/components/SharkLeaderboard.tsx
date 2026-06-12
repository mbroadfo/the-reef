import type { Shark } from '../types'
import SharkAvatar from './SharkAvatar'
import { getSharkColor } from '../utils/sharks'

export default function SharkLeaderboard({ sharks, compact = false }: { sharks: Shark[]; compact?: boolean }) {
  const displayed = compact ? sharks.slice(0, 5) : sharks

  if (!displayed.length) {
    return (
      <div className="text-slate-500 text-sm font-sans text-center py-8">
        No closed trades yet
      </div>
    )
  }

  return (
    <div>
      {displayed.map((s) => {
        const isPos  = s.total_pnl >= 0
        const color  = getSharkColor(s.name)
        const sign   = isPos ? '+' : ''

        return (
          <div
            key={s.name}
            className={`flex items-center gap-3 border-b border-reef-border last:border-0 ${compact ? 'py-2' : 'py-3'}`}
          >
            <SharkAvatar name={s.name} size="md" />

            <div className="flex-1 min-w-0">
              <div className="text-sm font-sans font-semibold truncate" style={{ color }}>
                {s.name}
              </div>
              <div className="text-xs font-sans text-slate-500">
                {s.trades} trade{s.trades !== 1 ? 's' : ''} · <span className="font-mono">{s.win_rate.toFixed(0)}%</span> win rate
              </div>
            </div>

            <div className="text-right shrink-0">
              <div className={`text-sm font-mono font-semibold ${isPos ? 'text-gain' : 'text-loss'}`}>
                {sign}${s.total_pnl.toFixed(2)}
              </div>
              {!compact && (
                <div className="text-xs font-mono text-slate-500">
                  avg {s.avg_pnl >= 0 ? '+' : '-'}${Math.abs(s.avg_pnl).toFixed(2)}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
