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

  const totalMv = positions.reduce((s, p) => s + p.market_value, 0)
  const totalPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0)
  const pnlPos = totalPnl >= 0

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-zinc-300 text-sm font-medium uppercase tracking-wider">
          Open Positions
          <span className="ml-2 text-zinc-600 font-normal">({positions.length})</span>
        </h1>
        {positions.length > 0 && (
          <div className="text-sm">
            <span className="text-zinc-500 mr-2">Equity ${totalMv.toFixed(2)}</span>
            <span className={pnlPos ? 'text-emerald-400' : 'text-red-400'}>
              {pnlPos ? '+' : ''}{totalPnl.toFixed(2)} unrealized
            </span>
          </div>
        )}
      </div>

      {loaded ? (
        <PositionsTable positions={positions} />
      ) : (
        <div className="text-zinc-600 text-sm animate-pulse">Loading...</div>
      )}
    </div>
  )
}
