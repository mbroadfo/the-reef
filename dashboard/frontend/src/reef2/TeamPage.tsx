import { Link, useParams } from 'react-router-dom'
import PodShark, { POD_HEX } from './PodShark'
import { DecisionChip, Loading, ResultChip, Section, Stat } from './ui'
import { dayLabel, num, pct, tone, usd } from './format'
import { useSnapshot } from './useSnapshot'

export default function TeamPage() {
  const { id } = useParams()
  const { snap, error } = useSnapshot()
  if (!snap) return <Loading error={error} />
  const pod = snap.pods.find(p => p.pod_id === id)
  if (!pod) return <div className="glass mt-8 p-6 text-slate-300">No such team. <Link className="underline" to="/">Back to the tank</Link></div>
  const active = pod.status === 'ACTIVE'
  const hex = POD_HEX[pod.pod_id]
  const rows = snap.proposals.filter(r => r.pod_id === pod.pod_id)
  return (
    <>
      <nav className="text-sm text-slate-400"><Link to="/" className="hover:text-white">Aquarium</Link> / <span className="text-slate-200">{pod.name}</span></nav>
      <div className="glass mt-3 flex flex-wrap items-center gap-4 p-4" style={{ borderColor: active ? `${hex}55` : undefined }}>
        <PodShark pod={pod} size={88} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-bold text-white">{pod.name}</h1>
            {active ? <span className="chip chip-funded">ACTIVE · #{pod.rank}</span> : <span className="chip chip-neutral">INACTIVE</span>}
          </div>
          <p style={{ color: hex }} className="font-semibold">{pod.tagline}</p>
          <p className="mt-1 text-slate-300">{pod.mandate}</p>
        </div>
      </div>

      {!active ? (
        <div className="glass mt-6 p-5 text-slate-300">
          <h2 className="text-lg font-bold text-white">Why this team is asleep</h2>
          <p className="mt-2">{pod.inactive_reason}</p>
          <p className="mt-2 text-sm text-slate-400">It has no capital sleeve, no proposals and no performance record. Nothing is shown for it because nothing has happened. It will wake when it has a working, tested strategy on point-in-time data and a funded sleeve approved by Mike.</p>
        </div>
      ) : (
        <>
          <div className="mt-5 grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="Sleeve NAV" value={usd(pod.nav)} sub={`funded ${usd(pod.funded)}`} />
            <Stat label="Return" value={<span className={tone(pod.return)}>{pct(pod.return, 2)}</span>} sub={`max drawdown ${pct(pod.max_drawdown, 1, false)}`} />
            <Stat label="Realized / unrealized" value={<span className={tone(pod.realized_pnl)}>{usd(pod.realized_pnl, true)}</span>} sub={<span className={tone(pod.unrealized_pnl)}>{usd(pod.unrealized_pnl, true)} open</span>} />
            <Stat label="Cash / invested" value={usd(pod.cash)} sub={`${usd(pod.invested)} invested · avg exposure ${pct(pod.avg_exposure, 0, false)}`} />
          </div>

          <Section title="Books" hint="NAV = funded + realized + unrealized, checked in the Research Lab">
            <div className="glass overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead><tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-400"><th className="px-3 py-2 text-left">Open position</th><th className="px-3 py-2 text-right">Shares</th><th className="px-3 py-2 text-right">Avg cost</th><th className="px-3 py-2 text-right">Last close</th><th className="px-3 py-2 text-right">Stop</th><th className="px-3 py-2 text-right">Unrealized</th></tr></thead>
                <tbody>
                  {pod.positions!.length === 0 && <tr><td colSpan={6} className="px-3 py-4 text-center text-slate-500">Flat: all cash.</td></tr>}
                  {pod.positions!.map(p => (
                    <tr key={p.symbol} className="border-b border-slate-800/60 last:border-0 font-mono">
                      <td className="px-3 py-2 text-left font-bold text-white">{p.symbol}</td><td className="px-3 py-2 text-right">{p.shares}</td>
                      <td className="px-3 py-2 text-right">{usd(p.avg_cost)}</td><td className="px-3 py-2 text-right">{usd(p.mark)}</td>
                      <td className="px-3 py-2 text-right">{usd(p.stop)}</td><td className={`px-3 py-2 text-right ${tone(p.unrealized)}`}>{usd(p.unrealized, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section title="Track record">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <Stat label="Closed trades" value={pod.trades} sub={`win rate ${pct(pod.win_rate, 0, false)}`} />
              <Stat label="Average win / loss" value={<span className="text-lg">{usd(pod.avg_win)} / {usd(pod.avg_loss)}</span>} />
              <Stat label="Volatility (ann.)" value={pct(pod.volatility_ann, 1, false)} sub={`return / risk ${num(pod.sharpe_like)}`} />
              <Stat label="Pitches funded" value={`${pod.funded_proposals} of ${pod.proposals}`} />
            </div>
          </Section>

          <Section title="Research desk" hint="Agents that prepare this team's evidence">
            <div className="glass p-4 text-sm text-slate-300">
              <p className="flex flex-wrap gap-2">{pod.research_agents.map(a => <span key={a} className="chip chip-neutral">{a}</span>)}</p>
              <p className="mt-2 text-slate-400">Strategy <span className="font-mono">{pod.strategy}</span>. Agents share one interface (a ticker and its point-in-time bars in, a verdict plus the figures behind it out), so an LLM-backed agent can join a desk later without changing Apex, Risk or the ledger.</p>
            </div>
          </Section>
        </>
      )}

      {active && (
        <Section title={`${pod.name}'s pitches`} hint="Click one to follow it end to end">
          <ul className="glass divide-y divide-slate-800/80 p-2">
            {rows.map(r => (
              <li key={r.proposal_id}>
                <Link to={`/proposal/${encodeURIComponent(r.proposal_id)}`} className="flex flex-wrap items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-white/5">
                  <span className="w-14 font-mono text-xs text-slate-500">{dayLabel(r.as_of_session)}</span>
                  <span className="font-mono font-bold text-white">{r.symbol}</span><DecisionChip row={r} /><ResultChip row={r} />
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  )
}
