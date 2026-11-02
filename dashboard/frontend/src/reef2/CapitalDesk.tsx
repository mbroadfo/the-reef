import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { POD_HEX } from './PodShark'
import { dayLabel, pct, tone, usd } from './format'
import type { CapitalReview, SessionView } from './replay'
import type { Timeline } from './Timeline'
import type { Snapshot } from './types'

const RESERVE_HEX = '#64748b'

// Apex's capital competition. Everything is read from the ledger events up to the viewed session: the reviews Apex has held,
// why, and what each sleeve controls now. Trading results and capital transfers are shown as different things on purpose.
function Bar({ snap, view }: { snap: Snapshot; view: SessionView }) {
  const parts = [
    ...view.pods.map(p => ({ id: p.pod_id, label: snap.pods.find(x => x.pod_id === p.pod_id)!.name, v: p.controlled, hex: POD_HEX[p.pod_id] })),
    { id: 'reserve', label: 'Central reserve', v: view.reserve, hex: RESERVE_HEX },
  ]
  return (
    <div>
      <div className="flex h-9 w-full overflow-hidden rounded-xl border border-slate-700" role="img"
           aria-label={parts.map(p => `${p.label} ${usd(p.v)}`).join(', ')}>
        {parts.map(p => (
          <div key={p.id} className="flex items-center justify-center overflow-hidden whitespace-nowrap px-1 font-mono text-xs font-bold text-slate-950"
               style={{ width: `${(p.v / view.fundNav) * 100}%`, background: p.hex }} title={`${p.label} ${usd(p.v)}`}>
            {(p.v / view.fundNav) > 0.17 ? usd(p.v) : ''}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-300">
        {parts.map(p => (
          <span key={p.id} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.hex }} />{p.label} <span className="font-mono text-slate-100">{usd(p.v)}</span>
            <span className="font-mono text-slate-500">{((p.v / view.fundNav) * 100).toFixed(0)}%</span>
          </span>
        ))}
        <span className="ml-auto font-mono text-slate-400">fund {usd(view.fundNav)}</span>
      </div>
    </div>
  )
}

function Transfer({ r, snap }: { r: CapitalReview; snap: Snapshot }) {
  const name = (id: string) => snap.pods.find(p => p.pod_id === id)?.name ?? id
  const to = r.transfers.find(t => t.amount > 0)
  const from = r.transfers.find(t => t.amount < 0)
  if (!to) return null
  const fromReserve = to.amount + (from?.amount ?? 0)
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {from && <span className="chip" style={{ color: POD_HEX[from.sleeve_id], background: `${POD_HEX[from.sleeve_id]}1a`, borderColor: `${POD_HEX[from.sleeve_id]}55` }}>{name(from.sleeve_id)} {usd(from.amount)}</span>}
      {fromReserve > 0 && <span className="chip chip-neutral">Reserve -{usd(fromReserve)}</span>}
      <span className="font-mono text-lg text-amber-200">▸</span>
      <span className="chip" style={{ color: POD_HEX[to.sleeve_id], background: `${POD_HEX[to.sleeve_id]}1a`, borderColor: `${POD_HEX[to.sleeve_id]}55` }}>{name(to.sleeve_id)} {usd(to.amount, true)}</span>
      <span className="text-xs text-slate-400">transferred; not a return</span>
    </div>
  )
}

function Evidence({ r, snap }: { r: CapitalReview; snap: Snapshot }) {
  const ids = snap.pods.map(p => p.pod_id).filter(id => id in r.evidence)
  const th = 'px-1.5 sm:px-2 py-1.5 text-right text-[10px] uppercase tracking-wider text-slate-400 font-semibold'
  const td = 'px-1.5 sm:px-2 py-1.5 text-right font-mono text-xs sm:text-sm'
  const rows: [string, (id: string) => string, ((id: string) => string)?][] = [
    ['Return, trailing window', id => pct(r.evidence[id].window_return, 2), id => tone(r.evidence[id].window_return)],
    ['Worst drawdown', id => pct(r.evidence[id].window_max_drawdown, 2, false)],
    ['Apex score (return - drawdown / 2)', id => pct(r.evidence[id].score, 2), id => tone(r.evidence[id].score)],
    ['Pitches in the window', id => `${r.evidence[id].proposals} / ${r.evidence[id].funded_proposals} funded`],
    ['Uncommitted cash', id => usd(r.evidence[id].free_cash)],
    ['Capital controlled', id => usd(r.evidence[id].sleeve_nav)],
  ]
  return (
    <div className="overflow-x-auto rounded-lg bg-slate-950/50">
      <table className="w-full">
        <thead><tr className="border-b border-slate-800">
          <th className={`${th} text-left`}>What Apex saw at the close</th>
          {ids.map(id => <th key={id} className={th} style={{ color: POD_HEX[id] }}>{snap.pods.find(p => p.pod_id === id)?.name}{r.leader === id && r.outcome === 'REALLOCATED' ? ' ▲' : r.trailer === id && r.outcome === 'REALLOCATED' ? ' ▼' : ''}</th>)}
        </tr></thead>
        <tbody>
          {rows.map(([label, f, t]) => (
            <tr key={label} className="border-b border-slate-800/60 last:border-0">
              <td className="px-2 py-1.5 text-left text-xs text-slate-300">{label}</td>
              {ids.map(id => <td key={id} className={`${td} ${t ? t(id) : 'text-slate-100'}`}>{f(id)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Chart({ snap, view, days }: { snap: Snapshot; view: SessionView; days: string[] }) {
  const data = useMemo(() => {
    const byDay = new Map(view.capital.map(c => [c.day, c]))
    return days.map(d => {
      const c = byDay.get(d)
      return c ? { day: d, ...c.pods, reserve: c.reserve } : { day: d }
    })
  }, [view, days])
  const ids = view.pods.map(p => p.pod_id)
  return (
    <div style={{ width: '100%', height: 220 }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 6, right: 8, left: -10, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
          <XAxis dataKey="day" tickFormatter={dayLabel} tick={{ fill: '#94a3b8', fontSize: 11 }} minTickGap={36} />
          <YAxis tickFormatter={v => `$${Math.round(Number(v) / 1000)}k`} tick={{ fill: '#94a3b8', fontSize: 11 }} domain={[0, Math.ceil(Number(snap.generated_from.initial_cash) * 1.1)]} />
          <Tooltip contentStyle={{ background: '#0f1726', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 12 }}
                   labelFormatter={l => dayLabel(String(l))} formatter={(v: number) => usd(v)} />
          {ids.map(id => <Area key={id} type="stepAfter" stackId="c" dataKey={id} name={snap.pods.find(p => p.pod_id === id)!.name} stroke={POD_HEX[id]} fill={POD_HEX[id]} fillOpacity={0.55} isAnimationActive={false} connectNulls={false} />)}
          <Area type="stepAfter" stackId="c" dataKey="reserve" name="Central reserve" stroke={RESERVE_HEX} fill={RESERVE_HEX} fillOpacity={0.35} isAnimationActive={false} connectNulls={false} />
          {view.reviews.map(r => <ReferenceLine key={r.review_id} x={r.day} stroke={r.outcome === 'REALLOCATED' ? '#fcd34d' : '#64748b'} strokeDasharray={r.outcome === 'REALLOCATED' ? undefined : '3 3'} strokeOpacity={0.8} />)}
          <ReferenceLine x={view.day} stroke="#67e8f9" strokeOpacity={0.6} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function CapitalDesk({ snap, tl }: { snap: Snapshot; tl: Timeline }) {
  const { view } = tl
  const [picked, setPicked] = useState<string | null>(null)
  const policy = snap.apex.capital_policy
  const every = Number(policy?.review_every ?? 10), first = Number(policy?.min_history ?? 15)
  const shown = view.reviews.find(r => r.review_id === picked) ?? view.reviews[view.reviews.length - 1]
  const nextNo = view.reviews.length ? view.reviews[view.reviews.length - 1].review_no + every : first
  const name = (id: string | null) => (id ? snap.pods.find(p => p.pod_id === id)?.name ?? id : '')
  const net = (id: string) => view.pods.find(p => p.pod_id === id)!
  return (
    <div className="glass p-3 sm:p-4">
      <Bar snap={snap} view={view} />

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="min-w-0">
          {shown ? (
            <div className="rounded-xl border bg-slate-950/60 p-3" style={{ borderColor: shown.outcome === 'REALLOCATED' ? 'rgba(252,211,77,0.5)' : 'rgba(100,116,139,0.5)' }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-300">Capital review {view.reviews.indexOf(shown) + 1}</span>
                <span className="text-xs text-slate-400">session {shown.index + 1} · {dayLabel(shown.day)}{shown.decided_today ? ' · decided at this close' : ''}</span>
                <span className={`chip ${shown.outcome === 'REALLOCATED' ? 'chip-warn' : 'chip-neutral'}`}>{shown.outcome === 'REALLOCATED' ? 'CAPITAL MOVED' : 'HELD'}</span>
              </div>
              <div className="mt-2"><Transfer r={shown} snap={snap} /></div>
              <p className="mt-2 text-sm leading-snug text-slate-200">{shown.rationale}</p>
              <div className="mt-3"><Evidence r={shown} snap={snap} /></div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <Link to={`/lab?seq=${shown.seq}`} className="rounded-full border border-slate-600 px-3 py-1.5 text-slate-200 hover:border-cyan-300/60">Decision: ledger #{shown.seq}</Link>
                {shown.transfers.filter(t => t.seq).map(t => (
                  <Link key={t.seq} to={`/lab?seq=${t.seq}`} className="rounded-full border border-slate-600 px-3 py-1.5 text-slate-200 hover:border-cyan-300/60">
                    {name(t.sleeve_id)} {usd(t.amount, true)}: ledger #{t.seq}
                  </Link>
                ))}
                <Link to="/lab#capital" className="rounded-full border border-cyan-300/50 bg-cyan-400/10 px-3 py-1.5 font-semibold text-cyan-100 hover:bg-cyan-400/20">Verify the transfers</Link>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-300">
              <p className="font-semibold text-white">No capital review yet.</p>
              <p className="mt-1 text-slate-400">The start stands: 30% each, 40% in the central reserve. Apex judges the teams for the first time at session {first}, once each has {first} sessions of record, and then every {every} sessions.</p>
            </div>
          )}
          <p className="mt-2 text-xs text-slate-500">Next review at session {nextNo}{nextNo > view.total ? ' (beyond this demonstration)' : ''}. Apex moves at most one step ({Number(policy?.step_pct ?? 0.05) * 100}% of the fund) per review, only uncommitted cash, and never sells a position to do it.</p>
        </div>

        <div className="min-w-0">
          <Chart snap={snap} view={view} days={tl.days} />
          <p className="text-xs text-slate-500">Bands change for two different reasons: slow slopes are trading results; steps at a gold line are Apex's transfers. A dotted line is a review that held.</p>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
            {view.pods.map(p => (
              <div key={p.pod_id} className="rounded-lg bg-slate-950/50 p-2">
                <dt className="font-semibold" style={{ color: POD_HEX[p.pod_id] }}>{name(p.pod_id)}</dt>
                <dd className="mt-0.5 font-mono text-slate-200">Started {usd(p.initial_funded)}</dd>
                <dd className="font-mono text-slate-200">Transfers <span className={tone(net(p.pod_id).net_transfers)}>{usd(p.net_transfers, true)}</span></dd>
                <dd className="font-mono text-slate-200">Trading P&amp;L <span className={tone(p.pnl)}>{usd(p.pnl, true)}</span></dd>
                <dd className="font-mono font-semibold text-white">= {usd(p.controlled)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {view.reviews.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-800/80 border-t border-slate-800">
          {[...view.reviews].reverse().map(r => {
            const to = r.transfers.find(t => t.amount > 0)
            return (
              <li key={r.review_id} className={`flex items-center gap-2 ${shown?.review_id === r.review_id ? 'bg-white/5' : ''}`}>
                <button onClick={() => { tl.stop(); setPicked(r.review_id) }} className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 px-1 py-2 text-left text-sm hover:bg-white/5">
                  <span className="w-24 font-mono text-xs text-slate-500">S{r.index + 1} · {dayLabel(r.day)}</span>
                  {to ? <span className="font-semibold text-amber-200">{name(to.sleeve_id)} {usd(to.amount, true)}</span> : <span className="text-slate-400">Held</span>}
                  <span className="min-w-0 flex-1 truncate text-xs text-slate-400">{to ? `from ${name(r.trailer)}${r.transfers.length === 1 ? ' and the reserve' : ''}` : r.reasons.join(', ').replace(/_/g, ' ').toLowerCase()}</span>
                </button>
                <button className="tl-btn shrink-0 px-2 text-[11px]" onClick={() => { tl.stop(); tl.go(r.index) }} aria-label={`Go to session ${r.index + 1}`}>go to session</button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
