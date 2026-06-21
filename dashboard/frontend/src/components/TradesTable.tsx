import { useNavigate } from 'react-router-dom'
import type { Trade } from '../types'
import SharkAvatar from './SharkAvatar'
import ConvictionBar from './ConvictionBar'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === 'open')        return <span className="text-blue-400 text-xs font-mono">open</span>
  if (outcome === 'closed_win')  return <span className="text-gain text-xs font-mono">win</span>
  if (outcome === 'closed_loss') return <span className="text-loss text-xs font-mono">loss</span>
  return <span className="text-slate-500 text-xs font-mono">{outcome}</span>
}

export default function TradesTable({ trades, compact = false, dashboard = false }: { trades: Trade[]; compact?: boolean; dashboard?: boolean }) {
  const navigate  = useNavigate()
  const displayed = (compact || dashboard) ? trades.slice(0, 8) : trades

  if (!displayed.length) {
    return (
      <div className="card flex items-center justify-center h-32 text-slate-500 text-sm font-sans">
        No trades yet
      </div>
    )
  }

  if (dashboard) {
    return (
      <div className="card overflow-x-auto">
        <table className="w-full" style={{ fontSize: '11px' }}>
          <thead>
            <tr className="border-b border-reef-border">
              {['Time', 'Shark', 'Symbol', 'Action', 'Qty', 'Price', 'Conf', 'P&L'].map((h) => (
                <th key={h} className="text-left text-slate-500 font-sans font-medium uppercase tracking-widest px-2 py-2" style={{ fontSize: '10px' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((t) => {
              const isBuy     = t.action === 'BUY'
              const pnlColor  = t.pnl == null ? '#64748b' : t.pnl >= 0 ? 'var(--reef-gain)' : 'var(--reef-loss)'
              const sharkName = normalizeSharkName(t.surfaced_by || 'Apex Shark')
              const color     = getSharkColor(sharkName)
              const conv      = t.conviction ?? 0
              return (
                <tr
                  key={t.id}
                  onClick={() => navigate(`/trades/${t.id}`)}
                  className="border-b border-reef-border/50 hover:bg-reef-elevated/30 transition-colors cursor-pointer"
                >
                  <td className="px-2 py-1.5 font-mono text-slate-500 whitespace-nowrap">
                    {new Date(t.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-1.5">
                      <SharkAvatar name={sharkName} size="sm" />
                      <span className="text-xs font-sans truncate" style={{ color, maxWidth: '80px' }}>{sharkName}</span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5 font-mono font-bold text-white">{t.ticker}</td>
                  <td className="px-2 py-1.5">
                    <span className={`font-mono font-semibold px-1.5 py-0.5 rounded border ${
                      isBuy ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                    }`} style={{ fontSize: '10px' }}>
                      {t.action}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 font-mono text-slate-300">{t.shares}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-300">${t.price.toFixed(2)}</td>
                  <td className="px-2 py-1.5">
                    <div style={{
                      width: '32px', height: '32px', borderRadius: '50%',
                      border: `2px solid ${color}`, display: 'flex', alignItems: 'center',
                      justifyContent: 'center', background: `${color}18`,
                    }}>
                      <span style={{ fontSize: '9px', fontFamily: 'JetBrains Mono', fontWeight: 700, color }}>{conv * 10}%</span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5 font-mono font-semibold" style={{ color: pnlColor }}>
                    {t.pnl == null ? '—' : `${t.pnl >= 0 ? '+' : '-'}$${Math.abs(t.pnl).toFixed(0)}`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-reef-border">
            {['#', 'Date', 'Action', 'Ticker', 'Shares', 'Price', 'P&L', 'Outcome', 'Shark'].map((h) => (
              <th key={h} className="text-left text-slate-500 text-xs font-sans font-medium uppercase tracking-widest px-4 py-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayed.map((t) => {
            const isBuy     = t.action === 'BUY'
            const pnlColor  = t.pnl == null ? '' : t.pnl >= 0 ? 'text-gain' : 'text-loss'
            const sharkName = normalizeSharkName(t.surfaced_by || 'Apex Shark')
            const color     = getSharkColor(sharkName)

            return (
              <tr
                key={t.id}
                onClick={() => navigate(`/trades/${t.id}`)}
                className="border-b border-reef-border/50 hover:bg-reef-elevated/30 transition-colors cursor-pointer"
              >
                <td className="px-4 py-3 text-slate-500 text-xs font-mono">{t.id}</td>
                <td className="px-4 py-3 text-slate-500 text-xs font-mono">{fmtDate(t.timestamp)}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded border ${
                    isBuy
                      ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                      : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  }`}>
                    {t.action}
                  </span>
                </td>
                <td className="px-4 py-3 font-bold font-mono text-white">{t.ticker}</td>
                <td className="px-4 py-3 font-mono text-slate-200">{t.shares}</td>
                <td className="px-4 py-3 font-mono text-slate-200">${t.price.toFixed(2)}</td>
                <td className={`px-4 py-3 font-mono ${pnlColor}`}>
                  {t.pnl == null ? '—' : `${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}`}
                </td>
                <td className="px-4 py-3">
                  <OutcomeBadge outcome={t.outcome} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <SharkAvatar name={t.surfaced_by} size="sm" />
                    <div className="min-w-0">
                      <div className="text-xs font-sans truncate" style={{ color }}>{sharkName}</div>
                      <ConvictionBar value={t.conviction} color={color} />
                    </div>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
