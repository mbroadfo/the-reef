import type { Shark } from '../types'

const DISPLAY: Record<string, string> = {
  momentum_shark: 'Momentum',
  earnings_shark: 'Earnings',
  news_shark: 'News',
  value_shark: 'Value',
  macro_shark: 'Macro',
  contrarian_shark: 'Contrarian',
  apex_shark: 'Apex',
}

const TIER: Record<string, string> = {
  momentum_shark: 'Hunter',
  earnings_shark: 'Hunter',
  news_shark: 'Hunter',
  value_shark: 'Analyst',
  macro_shark: 'Analyst',
  contrarian_shark: 'Analyst',
  apex_shark: 'PM',
}

export default function SharkLeaderboard({ sharks, compact = false }: { sharks: Shark[]; compact?: boolean }) {
  const displayed = compact ? sharks.slice(0, 5) : sharks

  if (!displayed.length) {
    return (
      <div className="text-zinc-600 text-sm text-center py-8">
        No closed trades yet
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {displayed.map((s, i) => {
        const isPos = s.total_pnl >= 0
        const pnlColor = isPos ? 'text-emerald-400' : 'text-red-400'
        const display = DISPLAY[s.name] ?? s.name
        const tier = TIER[s.name] ?? ''

        return (
          <div key={s.name} className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3">
            <span className="text-zinc-600 text-xs w-4">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-zinc-100 text-sm font-medium">{display} Shark</span>
                {tier && (
                  <span className="text-zinc-600 text-xs bg-zinc-800 px-1.5 py-0.5 rounded">
                    {tier}
                  </span>
                )}
              </div>
              <div className="text-zinc-500 text-xs">
                {s.trades} trade{s.trades !== 1 ? 's' : ''} · {s.win_rate.toFixed(0)}% win rate
              </div>
            </div>
            <div className="text-right">
              <div className={`font-bold font-mono text-sm ${pnlColor}`}>
                {isPos ? '+' : ''}{s.total_pnl.toFixed(2)}
              </div>
              <div className="text-zinc-600 text-xs">
                avg {s.avg_pnl >= 0 ? '+' : ''}{s.avg_pnl.toFixed(2)}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
