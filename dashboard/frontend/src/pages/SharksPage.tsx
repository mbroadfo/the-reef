import { useEffect, useState } from 'react'
import { fetchSharks, fetchDecisions } from '../api'
import type { Shark, Decision } from '../types'
import SharkLeaderboard from '../components/SharkLeaderboard'

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function SharksPage() {
  const [sharks, setSharks] = useState<Shark[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    Promise.all([fetchSharks(), fetchDecisions()])
      .then(([s, d]) => { setSharks(s); setDecisions(d); setLoaded(true) })
      .catch(() => setLoaded(true))
  }, [])

  if (!loaded) return <div className="max-w-7xl mx-auto px-4 py-12 text-zinc-600 text-sm animate-pulse">Loading...</div>

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-8">

      <div>
        <h1 className="text-zinc-300 text-sm font-medium uppercase tracking-wider mb-4">
          Shark Leaderboard
        </h1>
        {sharks.length ? (
          <SharkLeaderboard sharks={sharks} />
        ) : (
          <div className="text-zinc-600 text-sm">No closed trades yet — sharks haven't earned their stripes.</div>
        )}
      </div>

      {decisions.length > 0 && (
        <div>
          <h2 className="text-zinc-300 text-sm font-medium uppercase tracking-wider mb-4">
            Recent Apex Decisions
          </h2>
          <div className="space-y-3">
            {decisions.map((d, i) => {
              const isPos = d.decision === 'BUY'
              return (
                <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-zinc-100">{d.ticker}</span>
                    <span className={`text-xs font-bold ${isPos ? 'text-blue-400' : d.decision === 'PASS' ? 'text-zinc-500' : 'text-amber-400'}`}>
                      {d.decision}
                    </span>
                    <span className="text-zinc-600 text-xs">conv {d.conviction}/10</span>
                    <span className="text-zinc-600 text-xs ml-auto">{fmtDate(d.timestamp)}</span>
                  </div>
                  <div className="text-zinc-400 text-xs leading-relaxed line-clamp-3">{d.rationale}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
