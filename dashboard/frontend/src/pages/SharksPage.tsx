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

  if (!loaded) return (
    <div className="max-w-7xl mx-auto px-4 py-12 text-slate-500 text-sm font-sans animate-pulse">
      Loading...
    </div>
  )

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-8">

      <div>
        <h1 className="text-slate-200 text-sm font-sans font-medium uppercase tracking-widest mb-4">
          Shark Leaderboard
        </h1>
        {sharks.length ? (
          <SharkLeaderboard sharks={sharks} />
        ) : (
          <div className="text-slate-500 text-sm font-sans">
            No closed trades yet — sharks haven't earned their stripes.
          </div>
        )}
      </div>

      {decisions.length > 0 && (
        <div>
          <h2 className="text-slate-200 text-sm font-sans font-medium uppercase tracking-widest mb-4">
            Recent Apex Decisions
          </h2>
          <div className="space-y-3">
            {decisions.map((d, i) => {
              const isBuy  = d.decision === 'BUY'
              const isPass = d.decision === 'PASS'
              return (
                <div key={i} className="card p-4 space-y-2">
                  <div className="flex items-center gap-3">
                    <span className="font-bold font-mono text-white">{d.ticker}</span>
                    <span className={`text-xs font-mono font-bold ${isBuy ? 'text-blue-400' : isPass ? 'text-slate-500' : 'text-amber-400'}`}>
                      {d.decision}
                    </span>
                    <span className="text-slate-500 text-xs font-sans">conv <span className="font-mono">{d.conviction}/10</span></span>
                    <span className="text-slate-500 text-xs font-sans ml-auto">{fmtDate(d.timestamp)}</span>
                  </div>
                  <div className="text-slate-400 text-xs font-sans leading-relaxed line-clamp-3">{d.rationale}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
