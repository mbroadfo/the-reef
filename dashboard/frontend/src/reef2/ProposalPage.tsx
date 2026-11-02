import type { ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import PodShark, { POD_HEX } from './PodShark'
import { DecisionChip, Loading, PodChip, podById } from './ui'
import { dayLabel, pct, reasonLabel, tone, usd } from './format'
import { useSnapshot } from './useSnapshot'
import type { ProposalRow, Snapshot } from './types'

function Step({ n, title, accent, children }: { n: number; title: string; accent?: string; children: ReactNode }) {
  return (
    <section className="relative pl-12 pb-7">
      <span className="absolute left-0 top-0 grid h-9 w-9 place-items-center rounded-full border-2 bg-slate-950 font-mono text-sm font-bold"
            style={{ borderColor: accent ?? '#38bdf8', color: accent ?? '#7dd3fc' }}>{n}</span>
      <span className="absolute left-[17px] top-10 bottom-0 w-px bg-slate-700/70" aria-hidden />
      <h2 className="text-lg font-bold text-white">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  )
}

const LedgerRef = ({ seq, label }: { seq: number; label: string }) => (
  <Link to={`/lab?seq=${seq}`} className="chip chip-neutral hover:border-cyan-300/60" title="Open this ledger event in the Research Lab">
    ledger #{seq} · {label}
  </Link>
)

function Trace({ ok, title, children }: { ok: boolean | null; title: string; children: ReactNode }) {
  const color = ok === null ? 'text-slate-500' : ok ? 'text-gain' : 'text-loss'
  return (
    <li className="flex gap-3 py-2">
      <span className={`mt-0.5 w-5 text-center font-bold ${color}`} aria-label={ok === null ? 'not reached' : ok ? 'passed' : 'failed'}>{ok === null ? '-' : ok ? '✓' : '✗'}</span>
      <div className="min-w-0"><div className="font-semibold text-slate-100">{title}</div><div className="text-sm text-slate-400">{children}</div></div>
    </li>
  )
}

function PriceChart({ row, snap }: { row: ProposalRow; snap: Snapshot }) {
  const l = row.lifecycle!
  const path = snap.prices[row.symbol] ?? []
  const from = row.as_of_session, to = l.exit?.session_day ?? snap.generated_from.last_session
  const data = path.filter(([d]) => d >= from && d <= to).map(([d, c]) => ({ day: d, close: Number(c) }))
  const stop = Number(row.packet.exit_plan.stop_price)
  const hex = POD_HEX[row.pod_id]
  return (
    <div style={{ width: '100%', height: 220 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 10, left: -10, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
          <XAxis dataKey="day" tickFormatter={dayLabel} tick={{ fill: '#94a3b8', fontSize: 11 }} minTickGap={30} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} domain={['auto', 'auto']} tickFormatter={v => `$${v}`} />
          <Tooltip contentStyle={{ background: '#0f1726', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 12 }} labelFormatter={x => dayLabel(String(x))} formatter={(v: number) => usd(v)} />
          <ReferenceLine y={stop} stroke="#ff4444" strokeDasharray="4 3" label={{ value: `initial stop ${usd(stop)}`, fill: '#fca5a5', fontSize: 11, position: 'insideBottomRight' }} />
          {l.entry && <ReferenceLine x={l.entry.session_day} stroke={hex} label={{ value: 'bought', fill: hex, fontSize: 11, position: 'insideTopLeft' }} />}
          {l.exit && <ReferenceLine x={l.exit.session_day} stroke="#94a3b8" label={{ value: 'sold', fill: '#cbd5e1', fontSize: 11, position: 'insideTopRight' }} />}
          <Line type="monotone" dataKey="close" stroke={hex} strokeWidth={2.4} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function ProposalPage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const from = Number(params.get('s')) || null
  const { snap, error } = useSnapshot()
  if (!snap) return <Loading error={error} />
  const row = snap.proposals.find(r => r.proposal_id === id)
  if (!row) return <div className="glass mt-8 p-6 text-slate-300">No such proposal in this snapshot. <Link className="underline" to="/">Back to the tank</Link></div>
  const pod = podById(snap, row.pod_id)
  const pk = row.packet, d = row.decision!, l = row.lifecycle
  const funded = d.outcome === 'FUNDED'
  const accent = POD_HEX[row.pod_id]
  const rival = snap.pods.filter(p => p.status === 'ACTIVE' && p.pod_id !== pod.pod_id)
  const idx = snap.proposals.indexOf(row)
  const sizedAtOpen = l?.entry?.shares
  // The capital behind this pitch, from the ledger: what the pod controlled when Apex decided, the last review before that, and any
  // transfer that landed while the trade was open (which is capital, not P&L).
  const ev = snap.events
  const lastMark = [...ev].reverse().find(e => e.kind === 'SESSION_MARKED' && e.seq < d.seq)
  const controlledThen = lastMark ? Number((lastMark.payload as any).sleeve_nav[row.pod_id]) : null
  const reviewBefore = [...ev].reverse().find(e => e.kind === 'APEX_CAPITAL_DECISION' && e.seq < d.seq)
  const seqOfDay = (day?: string | null) => ev.find(e => e.kind === 'SESSION_MARKED' && (e.payload as any).session_day === day)?.seq
  const fromSeq = seqOfDay(l?.entry?.session_day) ?? 0
  const toSeq = l?.exit ? l.exit.seq : Infinity
  const moved = ev.filter(e => e.kind === 'SLEEVE_FUNDED' && (e.payload as any).ref !== 'd0-initial' && (e.payload as any).sleeve_id === row.pod_id && e.seq > fromSeq && e.seq < toSeq)
  const movedTotal = moved.reduce((a, e) => a + Number((e.payload as any).amount), 0)

  return (
    <>
      <nav className="text-sm text-slate-400"><Link to="/" className="hover:text-white">Aquarium</Link> / <Link to={`/team/${pod.pod_id}`} className="hover:text-white">{pod.name}</Link> / <span className="text-slate-200">{pk.symbol} · {dayLabel(pk.as_of_session)}</span></nav>

      {from !== null && from < snap.fund.nav_series.length && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border px-3 py-2 text-sm" style={{ borderColor: 'rgba(245,158,11,0.5)', background: 'rgba(245,158,11,0.08)' }}>
          <span className="chip chip-warn">COMPLETE RECORD</span>
          <span className="text-slate-200">You opened this from session {from} of the replay. This story shows everything that happened afterward too, through the end of the demonstration.</span>
          <Link to={`/?s=${from}&p=${encodeURIComponent(row.proposal_id)}`} className="ml-auto text-cyan-300 hover:underline">Back to the replay at session {from}</Link>
        </div>
      )}
      <div className="glass mt-3 flex flex-wrap items-center gap-4 p-4" style={{ borderColor: `${accent}55` }}>
        <PodShark pod={pod} size={64} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><PodChip pod={pod} /><DecisionChip row={row} />{l?.status === 'CLOSED' && <span className={`chip ${Number(l.pnl) >= 0 ? 'chip-funded' : 'chip-declined'}`}>{usd(l.pnl, true)}</span>}</div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-bold text-white"><span className="font-mono">{pk.symbol}</span> <span className="text-slate-400 text-xl">pitched {dayLabel(pk.as_of_session)}</span></h1>
        </div>
      </div>

      <div className="mt-6">
        <Step n={1} title={`${pod.name}'s research desk looked at ${pk.symbol}`} accent={accent}>
          <div className="grid gap-3 sm:grid-cols-2">
            {pk.findings.map(f => (
              <div key={f.agent} className="glass p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-slate-100">{f.role}</span>
                  <span className={`chip ${f.verdict === 'support' ? 'chip-funded' : f.verdict === 'oppose' ? 'chip-declined' : 'chip-neutral'}`}>{f.verdict.toUpperCase()}</span>
                </div>
                <p className="mt-1 text-sm text-slate-400">{f.summary}</p>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
                  {f.metrics.map(m => <div key={m.label} className="contents"><dt className="text-slate-500">{m.label}</dt><dd className="text-right font-mono text-slate-200">{m.value}</dd></div>)}
                </dl>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">Deterministic agents today ({pod.research_agents.join(', ')}); every figure is recomputable from the point-in-time bars. An LLM agent can plug into the same interface later.</p>
        </Step>

        <Step n={2} title="The pitch to Apex" accent={accent}>
          <blockquote className="border-l-2 pl-3 text-slate-200" style={{ borderColor: accent }}>{pk.thesis}</blockquote>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <div className="glass p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">Entry plan</div><div className="mt-1 text-sm text-slate-200">Buy at the next valid open</div><div className="text-xs text-slate-400">Reference {usd(pk.entry_plan.reference_price)}, {pk.entry_plan.reference}</div></div>
            <div className="glass p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">Exit plan</div><div className="mt-1 text-sm text-slate-200">Stop {usd(pk.exit_plan.stop_price)} ({pk.risk.stop_distance_pct}% away)</div><ul className="text-xs text-slate-400 list-disc pl-4">{pk.exit_plan.rules.map(r => <li key={r}>{r}</li>)}</ul></div>
            <div className="glass p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">Capital request</div><div className="mt-1 text-sm text-slate-200">{usd(pk.capital_request.dollars)} ({pk.capital_request.shares} shares)</div><div className="text-xs text-slate-400">Risks {usd(pk.risk.risk_at_request)} to the stop if fully filled</div></div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2"><LedgerRef seq={row.packet_seq} label="PROPOSAL_SUBMITTED" /><span className="chip chip-neutral">{pk.strategy}</span></div>
        </Step>

        <Step n={3} title={funded ? 'Apex funded it' : 'Apex declined it'} accent={funded ? '#00ff88' : '#ff4444'}>
          <div className="glass p-3">
            <ul className="divide-y divide-slate-800/70">
              <Trace ok={!d.reasons.includes('D0_RANK_CAP')} title={`Rank: #${d.rank} of ${d.of} from ${pod.name}`}>
                Apex's D0 rule funds at most {d.max_new_per_session} new position{d.max_new_per_session > 1 ? 's' : ''} per pod per session, best score first.
              </Trace>
              <Trace ok={null} title={`Whose capital: ${pod.name} controlled ${controlledThen === null ? '-' : usd(controlledThen)} at this decision`}>
                {reviewBefore
                  ? <>Apex's latest capital review before this was <LedgerRef seq={reviewBefore.seq} label="capital review" />: {String((reviewBefore.payload as any).rationale)}</>
                  : 'No capital review had happened yet: the original 30/30/40 split applied.'}
              </Trace>
              <Trace ok={d.reasons.includes('D0_RANK_CAP') ? null : !d.reasons.includes('SIZE_ZERO')} title={d.ceiling_shares !== undefined ? `Capital: asked ${d.requested_shares} sh, D0 ceiling ${d.ceiling_shares} sh, granted ${d.granted_shares} sh` : 'Capital'}>
                {d.ceiling_shares !== undefined ? <>Pod cash {usd(d.sleeve_cash)}. Granted {usd(d.granted_dollars)} at most; Apex never grants more than the pod asked for.</> : 'Not reached: the idea was outranked first.'}
              </Trace>
              <Trace ok={d.reasons.includes('D0_RANK_CAP') || d.reasons.includes('SIZE_ZERO') ? null : !d.reasons.includes('INSTRUMENT_NOT_TRADABLE')} title="Gate: is it tradable at the next open?">
                {d.reasons.includes('INSTRUMENT_NOT_TRADABLE') ? 'No. ' : 'Yes. '}Calendar, instrument status and pending corporate actions were checked as of the decision time.
              </Trace>
              <Trace ok={d.reasons.includes('D0_RANK_CAP') || d.reasons.includes('SIZE_ZERO') || d.reasons.includes('INSTRUMENT_NOT_TRADABLE') ? null : !d.reasons.includes('RISK_REJECTED')}
                     title={d.risk_check_shares ? `Risk Engine pre-check: up to ${d.risk_check_shares} shares` : 'Risk Engine pre-check'}>
                Sizes to the 0.5% risk rule, the 10% position cap and the sleeve's cash, against the whole fund's exposure.
              </Trace>
              <Trace ok={funded ? (l?.status === 'NOT_FILLED' ? false : true) : null} title={funded ? `Queued for ${d.fill_session}'s open` : 'Not queued'}>
                {funded ? 'The order waits for the official open of the next valid session; no price is assumed in advance.' : 'Nothing was queued.'}
              </Trace>
            </ul>
            <div className={`mt-2 rounded-lg p-3 text-sm ${funded ? 'bg-emerald-400/10 text-emerald-200' : 'bg-red-400/10 text-red-200'}`}>
              <strong>{funded ? 'Verdict: funded.' : `Verdict: declined (${reasonLabel(d.reasons)}).`}</strong>{' '}
              {row.decision_explained.length > 0 ? row.decision_explained.join(' ') : d.detail}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2"><LedgerRef seq={d.seq} label="APEX_DECISION" />{row.order && <LedgerRef seq={row.order.seq} label="ORDER_QUEUED" />}</div>
        </Step>

        {funded && l?.entry && (
          <>
            <Step n={4} title="It was bought at the next open" accent={accent}>
              <p className="text-slate-300">
                <span className="font-mono text-white">{l.entry.shares}</span> shares at <span className="font-mono text-white">{usd(l.entry.price)}</span> on {dayLabel(l.entry.session_day)}
                {' '}({usd(l.entry.cost)}). Apex's ceiling was {d.granted_shares} shares; the Risk Engine sized the fill to {sizedAtOpen} at the actual open price.
              </p>
              <div className="mt-2"><LedgerRef seq={l.entry.seq} label="FILL" /></div>
            </Step>
            <Step n={5} title="What happened next" accent={accent}>
              <div className="glass p-3"><PriceChart row={row} snap={snap} /></div>
              <p className="mt-2 text-sm text-slate-300">
                {l.stop_raises && l.stop_raises.length > 0 ? `The stop was raised ${l.stop_raises.length} time${l.stop_raises.length > 1 ? 's' : ''}, to ${usd(l.stop_raises[l.stop_raises.length - 1].stop_price)}. ` : 'The stop never moved. '}
                {l.exit ? <>{l.exit.reason}. Sold {l.exit.shares} at <span className="font-mono">{usd(l.exit.price)}</span> on {dayLabel(l.exit.session_day)}.</> : 'The position is still open at the end of the demonstration.'}
              </p>
              {l.exit && <div className="mt-2"><LedgerRef seq={l.exit.seq} label="FILL (exit)" /></div>}
            </Step>
            <Step n={6} title={`Who benefited: ${pod.name}`} accent={Number(l.pnl) >= 0 ? '#00ff88' : '#ff4444'}>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="glass p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">{l.status === 'OPEN' ? 'Unrealized P&L' : 'Realized P&L'}</div><div className={`mt-1 font-mono text-2xl font-bold ${tone(l.pnl)}`}>{usd(l.pnl, true)}</div><div className={`text-xs ${tone(l.return)}`}>{pct(l.return, 2)} on the position</div></div>
                <div className="glass p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">{pod.name} sleeve</div><div className="mt-1 font-mono text-lg text-white">{usd(l.sleeve_nav_before)} → {usd(l.sleeve_nav_after)}</div><div className={`text-xs ${tone(l.sleeve_return_contribution)}`}>{pct(l.sleeve_return_contribution, 2)} of the sleeve's capital</div>
                  {moved.length > 0 && <div className="mt-1 text-xs text-amber-200">Includes {usd(movedTotal, true)} moved by Apex while this trade was open: capital, not profit.</div>}</div>
                <div className="glass p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">Whole fund</div><div className={`mt-1 font-mono text-2xl font-bold ${tone(l.fund_return_contribution)}`}>{pct(l.fund_return_contribution, 2)}</div><div className="text-xs text-slate-400">of the $10,000 fund</div></div>
              </div>
              <p className="mt-2 text-sm text-slate-400">
                Standing at the end of the demonstration: {pod.name} {pct(pod.return, 2)} (#{pod.rank})
                {rival.map(r => <span key={r.pod_id}>, {r.name} {pct(r.return, 2)} (#{r.rank})</span>)}.
                Sleeve NAVs are the ledger's verified end-of-session valuations; the other pod's books are untouched by this trade.
              </p>
            </Step>
          </>
        )}

        {funded && l?.status === 'NOT_FILLED' && (
          <Step n={4} title="The order did not fill" accent="#ff4444"><p className="text-slate-300">It was queued, but the fill was refused at the open ({l.reason}). Nothing was bought.</p></Step>
        )}

        {!funded && (
          <Step n={4} title="Nothing was traded" accent="#64748b">
            <p className="text-slate-300">No order, no fill, no effect on any sleeve or on the fund.</p>
            {row.counterfactual && (
              <p className="mt-2 rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-sm text-slate-400">
                <span className="chip chip-warn mr-2">HYPOTHETICAL</span>
                For context only: the price moved {pct(row.counterfactual.move, 1)} from the pitch's {usd(row.counterfactual.ref_price)} reference to {usd(row.counterfactual.last_close)} by {dayLabel(row.counterfactual.through)}.
                This ignores stops, sizing and costs, and was not traded.
              </p>
            )}
          </Step>
        )}
      </div>

      <div className="mt-2 flex justify-between text-sm">
        {idx > 0 ? <Link className="text-cyan-300 hover:underline" to={`/proposal/${encodeURIComponent(snap.proposals[idx - 1].proposal_id)}`}>← previous pitch</Link> : <span />}
        {idx < snap.proposals.length - 1 ? <Link className="text-cyan-300 hover:underline" to={`/proposal/${encodeURIComponent(snap.proposals[idx + 1].proposal_id)}`}>next pitch →</Link> : <span />}
      </div>
    </>
  )
}
