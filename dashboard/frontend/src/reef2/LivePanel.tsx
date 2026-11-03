import { Link } from 'react-router-dom'
import { Section } from './ui'
import { dayLabel, pct, tone, usd } from './format'
import type { LiveBlock, Snapshot } from './types'

const ET = 'America/New_York'
const when = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString('en-US', { timeZone: ET, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : '-'

const FRESH: Record<string, { chip: string; text: string }> = {
  CURRENT: { chip: 'chip-funded', text: 'CURRENT' },
  AWAITING_VENDOR: { chip: 'chip-warn', text: 'AWAITING DATA' },
  STALE: { chip: 'chip-declined', text: 'STALE' },
}

export const isLive = (snap: Snapshot): snap is Snapshot & { live: LiveBlock } => snap.mode.kind === 'LIVE_DATA_PAPER' && !!snap.live

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass px-4 py-3 min-w-0">
      <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</div>
      <div className="mt-1 truncate text-lg font-bold font-mono text-white">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-400">{sub}</div>}
    </div>
  )
}

export function LiveStatusBar({ live }: { live: LiveBlock }) {
  const f = FRESH[live.data.freshness]
  const hold = live.run && (live.run.status === 'SAFE_HOLD' || live.run.status === 'ERROR')
  return (
    <div role="status" className="relative z-20 flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1.5 text-xs"
         style={{ background: 'rgba(8,145,178,0.12)', borderBottom: '1px solid rgba(34,211,238,0.35)', color: '#e2e8f0' }}>
      <span className="chip chip-neutral">PAPER MONEY ONLY</span>
      <span className={`chip ${f.chip}`} title={`Provider: ${live.data.provider}`}>DATA {f.text}</span>
      <span className="text-slate-300">last bar {live.data.last_bar_session ? dayLabel(live.data.last_bar_session) : '-'} · checked {when(live.data.checked_at)}</span>
      {hold && <span className="chip chip-declined">{live.run!.status.replace('_', ' ')}: nothing advanced</span>}
    </div>
  )
}

export default function LivePanel({ snap }: { snap: Snapshot & { live: LiveBlock } }) {
  const live = snap.live
  const f = FRESH[live.data.freshness]
  const pods = snap.pods.filter(p => p.status === 'ACTIVE')
  const reviews = snap.events.filter(e => e.kind === 'APEX_CAPITAL_DECISION').slice(-3).reverse()
  const recent = [...snap.proposals].reverse().slice(0, 8)
  const alerts: string[] = []
  if (live.run && live.run.status !== 'ADVANCED' && live.run.status !== 'UP_TO_DATE') alerts.push(...live.run.reasons.map(r => `${live.run!.status}: ${r}`))
  for (const [s, why] of Object.entries(live.holds)) alerts.push(`${s} is on hold - ${why.join('; ')}`)
  if (live.catch_up_sessions.length) alerts.push(`${live.catch_up_sessions.length} session(s) were processed late, in order (${live.catch_up_sessions.map(dayLabel).join(', ')}); decisions used only data final at each close.`)
  for (const [d, m] of Object.entries(live.uncredited_dividends)) alerts.push(`${dayLabel(d)}: ex-dividend on held ${Object.entries(m).map(([s, a]) => `${s} $${a}/sh`).join(', ')} - reported, not credited (price-return accounting).`)
  const th = 'px-2 py-2 text-right text-[11px] uppercase tracking-wider text-slate-400 font-semibold'
  const td = 'px-2 py-2 text-right font-mono text-sm'
  return (
    <>
      <div className="pt-1">
        <h1 className="text-2xl font-bold leading-tight text-white sm:text-4xl">Two sharks, real markets. <span className="text-cyan-300">Paper money.</span></h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-300">
          Momentum and Contrarian trade a ${Number(snap.generated_from.initial_cash).toLocaleString()} paper fund on real daily bars, one session at a time, under the same Risk Engine and Apex rules as the demonstration.
          Orders are decided at a close and filled, in the books only, at the next session's open price. {live.execution.meaning}
        </p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Fact label="Fund NAV" value={usd(snap.fund.nav)} sub={`${pct(snap.fund.return, 2)} since ${dayLabel(live.first_session)}`} />
        <Fact label="Data as of" value={live.data.last_bar_session ? dayLabel(live.data.last_bar_session) : '-'} sub={`${f.text.toLowerCase()} · expects ${live.data.expected_session ? dayLabel(live.data.expected_session) : '-'}`} />
        <Fact label="Sessions processed" value={String(live.sessions.processed)} sub={live.sessions.last_processed ? `last ${dayLabel(live.sessions.last_processed)}` : 'waiting for the first close'} />
        <Fact label="Next session" value={live.sessions.next ? dayLabel(live.sessions.next.day) : '-'}
              sub={live.sessions.next ? `${when(live.sessions.next.open)} - ${new Date(live.sessions.next.close).toLocaleTimeString('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit' })}${live.sessions.next.early_close ? ' (early close)' : ''}` : undefined} />
      </div>

      <div className="glass mt-3 p-3 text-xs leading-relaxed text-slate-300">
        <strong className="text-cyan-200">How fills are known.</strong> A fill is written only after the session's daily bar is final and complete ({live.data.final_after_minutes} minutes after the close, benchmark and coverage checked).
        It is a <em>simulated fill reconstructed from daily open/high/low</em>, not a live intraday execution, and nothing is sent to a broker. If a price cannot be trusted the order is refused and the name is left unmarked.
        {' '}{live.attested_sessions} sessions carry a signed data digest in the ledger. Epoch <span className="font-mono">{live.epoch_id}</span>, opened {when(live.activated_at)}.
      </div>

      {alerts.length > 0 && (
        <ul className="mt-3 space-y-1 rounded-xl border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-amber-100" aria-label="Attention">
          {alerts.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      )}

      <Section title="Positions and NAV" hint="Marked at the official close of the last processed session">
        <div className="glass overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead><tr className="border-b border-slate-800">
              <th className={`${th} text-left`}>Team</th><th className={th}>NAV</th><th className={th}>Cash</th><th className={th}>Return</th><th className={th}>Position</th><th className={th}>Shares</th><th className={th}>Cost</th><th className={th}>Mark</th><th className={th}>Stop</th><th className={th}>Unrealized</th>
            </tr></thead>
            <tbody>
              {pods.flatMap(p => {
                const rows = p.positions && p.positions.length ? p.positions : [null]
                return rows.map((pos, i) => (
                  <tr key={`${p.pod_id}-${pos?.symbol ?? 'none'}`} className="border-b border-slate-800/60">
                    <td className="px-2 py-2 text-left font-semibold text-white">{i === 0 ? p.name : ''}</td>
                    <td className={td}>{i === 0 ? usd(p.nav) : ''}</td><td className={td}>{i === 0 ? usd(p.cash) : ''}</td>
                    <td className={`${td} ${tone(p.return)}`}>{i === 0 ? pct(p.return, 2) : ''}</td>
                    {pos ? (<>
                      <td className={td}>{pos.symbol}</td><td className={td}>{pos.shares}</td><td className={td}>{usd(pos.avg_cost)}</td><td className={td}>{usd(pos.mark)}</td>
                      <td className={td}>{pos.stop ? usd(pos.stop) : '-'}</td><td className={`${td} ${tone(pos.unrealized)}`}>{usd(pos.unrealized, true)}</td>
                    </>) : <td className={`${td} text-slate-500`} colSpan={6}>no open position</td>}
                  </tr>
                ))
              })}
              <tr><td className="px-2 py-2 text-left text-slate-400">Apex reserve</td><td className={td}>{usd(snap.fund.unallocated)}</td><td className={td} colSpan={8} />
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Queued for the next open" hint="Decided at the last close; they fill (in the books) at the next session's official open, if the data and the Risk Engine allow">
        <div className="glass p-3 text-sm">
          {live.pending_orders.length === 0 ? <span className="text-slate-500">Nothing queued.</span> : (
            <ul className="divide-y divide-slate-800/80">
              {live.pending_orders.map((o, i) => (
                <li key={i} className="flex flex-wrap items-center gap-x-3 py-2">
                  <span className="font-semibold text-white">{o.sleeve_id}</span><span className="font-mono">{o.intent} up to {o.shares} {o.symbol}</span>
                  <span className="text-slate-400">ref {o.ref_price ? usd(o.ref_price) : '-'} · stop {o.stop ? usd(o.stop) : '-'} · fills {dayLabel(o.fill_session)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Section>

      <Section title="Apex decisions" hint="Latest pitches and capital reviews, from the ledger">
        <div className="glass p-3 text-sm">
          {reviews.map(e => {
            const p = e.payload as Record<string, any>
            return (
              <p key={e.seq} className="border-b border-slate-800/80 pb-2 text-slate-300">
                <span className="chip chip-neutral mr-2">REVIEW {String(p.review_id).replace('review-', '#')}</span><strong>{p.outcome}</strong>: {p.rationale}{' '}
                <Link to={`/lab?seq=${e.seq}`} className="text-cyan-300 hover:underline">ledger #{e.seq}</Link>
              </p>
            )
          })}
          {reviews.length === 0 && <p className="border-b border-slate-800/80 pb-2 text-slate-500">No capital review yet (the first is after {snap.apex.capital_policy?.min_history} sessions).</p>}
          <ul className="divide-y divide-slate-800/80">
            {recent.length === 0 && <li className="py-2 text-slate-500">No pitches yet.</li>}
            {recent.map(r => (
              <li key={r.proposal_id} className="flex flex-wrap items-center gap-x-3 py-2">
                <span className="w-14 font-mono text-xs text-slate-500">{dayLabel(r.as_of_session)}</span>
                <span className="font-semibold text-white">{r.pod_id}</span><span className="font-mono font-bold">{r.symbol}</span>
                {r.decision?.outcome === 'FUNDED' ? <span className="chip chip-funded">FUNDED</span> : <span className="chip chip-declined">DECLINED{r.decision ? ` · ${r.decision.reasons.join(' + ')}` : ''}</span>}
                <Link to={`/proposal/${encodeURIComponent(r.proposal_id)}`} className="text-cyan-300 hover:underline">pitch</Link>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <Section title="Ledger and checks">
        <div className="glass p-3 text-sm text-slate-300">
          <ul className="space-y-1">{snap.checks.map(c => <li key={c.name}><span className={`chip ${c.ok ? 'chip-funded' : 'chip-declined'} mr-2`}>{c.ok ? 'OK' : 'FAIL'}</span>{c.name} <span className="text-slate-500">- {c.detail}</span></li>)}</ul>
          <p className="mt-2"><Link to="/lab" className="text-cyan-300 hover:underline">Verify the hash chain and every balance in your browser</Link> · charter <span className="font-mono text-xs">{live.charter_hash?.slice(0, 16)}</span></p>
        </div>
      </Section>
    </>
  )
}
