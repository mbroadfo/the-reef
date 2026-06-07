import type { Position } from '../types'

function fmtShark(name: string): string {
  return name.replace('_shark', '').replace('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg flex items-center justify-center h-32 text-zinc-600 text-sm">
        No open positions
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800">
            {['Ticker', 'Shares', 'Entry', 'Current', 'P&L', 'P&L %', 'Stop', 'Target', 'Conv', 'Hunter'].map((h) => (
              <th key={h} className="text-left text-zinc-500 text-xs font-medium uppercase tracking-wider px-4 py-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const isPos = p.unrealized_pnl >= 0
            const pnlColor = isPos ? 'text-emerald-400' : 'text-red-400'
            return (
              <tr key={p.ticker} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className="px-4 py-3 font-bold text-blue-400">{p.ticker}</td>
                <td className="px-4 py-3 text-zinc-300">{p.shares}</td>
                <td className="px-4 py-3 text-zinc-300">${p.entry_price.toFixed(2)}</td>
                <td className="px-4 py-3 text-zinc-100">${p.current_price.toFixed(2)}</td>
                <td className={`px-4 py-3 font-mono font-medium ${pnlColor}`}>
                  {isPos ? '+' : ''}{p.unrealized_pnl.toFixed(2)}
                </td>
                <td className={`px-4 py-3 font-mono ${pnlColor}`}>
                  {isPos ? '+' : ''}{p.unrealized_pnl_pct.toFixed(1)}%
                </td>
                <td className="px-4 py-3 text-zinc-500">
                  {p.stop_loss != null ? `$${p.stop_loss.toFixed(2)}` : '—'}
                </td>
                <td className="px-4 py-3 text-zinc-500">
                  {p.target_price != null ? `$${p.target_price.toFixed(2)}` : '—'}
                </td>
                <td className="px-4 py-3 text-zinc-400">{p.conviction}</td>
                <td className="px-4 py-3 text-zinc-500 text-xs">{fmtShark(p.surfaced_by)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
