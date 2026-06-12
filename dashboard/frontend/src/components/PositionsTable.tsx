import type { Position } from '../types'

export default function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <div className="card flex items-center justify-center h-32 text-slate-500 text-sm font-sans">
        No open positions
      </div>
    )
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-reef-border">
            {['Ticker', 'Shares', 'Entry', 'Current', 'P&L', 'P&L %', 'Stop', 'Target', 'Conv', 'Shark'].map((h) => (
              <th key={h} className="text-left text-slate-500 text-xs font-sans font-medium uppercase tracking-widest px-4 py-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const isPos = p.unrealized_pnl >= 0
            const pnlColor = isPos ? 'text-gain' : 'text-loss'
            return (
              <tr key={p.ticker} className="border-b border-reef-border/50 hover:bg-reef-elevated/30 transition-colors">
                <td className="px-4 py-3 font-bold font-mono text-blue-400">{p.ticker}</td>
                <td className="px-4 py-3 font-mono text-slate-200">{p.shares}</td>
                <td className="px-4 py-3 font-mono text-slate-200">${p.entry_price.toFixed(2)}</td>
                <td className="px-4 py-3 font-mono text-white">${p.current_price.toFixed(2)}</td>
                <td className={`px-4 py-3 font-mono font-medium ${pnlColor}`}>
                  {isPos ? '+' : ''}{p.unrealized_pnl.toFixed(2)}
                </td>
                <td className={`px-4 py-3 font-mono ${pnlColor}`}>
                  {isPos ? '+' : ''}{p.unrealized_pnl_pct.toFixed(1)}%
                </td>
                <td className="px-4 py-3 font-mono text-slate-500">
                  {p.stop_loss != null ? `$${p.stop_loss.toFixed(2)}` : '—'}
                </td>
                <td className="px-4 py-3 font-mono text-slate-500">
                  {p.target_price != null ? `$${p.target_price.toFixed(2)}` : '—'}
                </td>
                <td className="px-4 py-3 font-mono text-slate-400">{p.conviction}</td>
                <td className="px-4 py-3 text-slate-500 text-xs font-sans">{p.surfaced_by}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
