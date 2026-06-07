import { useNavigate } from 'react-router-dom'
import type { Trade } from '../types'

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function fmtShark(name: string): string {
  return name.replace('_shark', '').replace('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === 'open') return <span className="text-blue-400 text-xs">open</span>
  if (outcome === 'closed_win') return <span className="text-emerald-400 text-xs">win</span>
  if (outcome === 'closed_loss') return <span className="text-red-400 text-xs">loss</span>
  return <span className="text-zinc-500 text-xs">{outcome}</span>
}

export default function TradesTable({ trades, compact = false }: { trades: Trade[]; compact?: boolean }) {
  const navigate = useNavigate()
  const displayed = compact ? trades.slice(0, 8) : trades

  if (!displayed.length) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg flex items-center justify-center h-32 text-zinc-600 text-sm">
        No trades yet
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800">
            {['#', 'Date', 'Action', 'Ticker', 'Shares', 'Price', 'P&L', 'Outcome', 'Hunter'].map((h) => (
              <th key={h} className="text-left text-zinc-500 text-xs font-medium uppercase tracking-wider px-4 py-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayed.map((t) => {
            const isBuy = t.action === 'BUY'
            const pnlColor = t.pnl == null ? '' : t.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
            return (
              <tr
                key={t.id}
                onClick={() => navigate(`/trades/${t.id}`)}
                className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors cursor-pointer"
              >
                <td className="px-4 py-3 text-zinc-600 text-xs">{t.id}</td>
                <td className="px-4 py-3 text-zinc-500 text-xs">{fmtDate(t.timestamp)}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-bold ${isBuy ? 'text-blue-400' : 'text-amber-400'}`}>
                    {t.action}
                  </span>
                </td>
                <td className="px-4 py-3 font-bold text-zinc-100">{t.ticker}</td>
                <td className="px-4 py-3 text-zinc-300">{t.shares}</td>
                <td className="px-4 py-3 text-zinc-300">${t.price.toFixed(2)}</td>
                <td className={`px-4 py-3 font-mono ${pnlColor}`}>
                  {t.pnl == null ? '—' : `${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}`}
                </td>
                <td className="px-4 py-3">
                  <OutcomeBadge outcome={t.outcome} />
                </td>
                <td className="px-4 py-3 text-zinc-500 text-xs">{fmtShark(t.surfaced_by)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
