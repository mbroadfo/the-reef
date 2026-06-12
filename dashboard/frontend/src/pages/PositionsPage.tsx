import { useEffect, useState } from 'react'
import { fetchPositions } from '../api'
import type { Position } from '../types'
import PositionsTable from '../components/PositionsTable'

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetchPositions().then((p) => {
      setPositions(p)
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [])

  const totalMv  = positions.reduce((s, p) => s + p.market_value, 0)
  const totalPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0)
  const pnlPos   = totalPnl >= 0

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-slate-200 text-sm font-sans font-medium uppercase tracking-widest">
          Open Positions
          <span className="ml-2 text-slate-500 font-normal">({positions.length})</span>
        </h1>
        {positions.length > 0 && (
          <div className="text-sm font-sans">
            <span className="text-slate-500 mr-2">Equity <span className="font-mono">${totalMv.toFixed(2)}</span></span>
            <span className={pnlPos ? 'text-gain' : 'text-loss'}>
              <span className="font-mono">{pnlPos ? '+' : ''}{totalPnl.toFixed(2)}</span> unrealized
            </span>
          </div>
        )}
      </div>

      {loaded ? (
        <PositionsTable positions={positions} />
      ) : (
        <div className="text-slate-500 text-sm animate-pulse">Loading...</div>
      )}
    </div>
  )
}
