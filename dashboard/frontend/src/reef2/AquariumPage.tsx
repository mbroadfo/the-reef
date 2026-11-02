import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import PodShark, { POD_HEX } from './PodShark'
import { ApexColumn, Contender } from './Arena'
import { TimelineBar, useTimeline } from './Timeline'
import type { Timeline } from './Timeline'
import CapitalDesk from './CapitalDesk'
import { Loading, PodChip, Section, podById } from './ui'
import { dayLabel, num, pct, reasonLabel, tone, usd } from './format'
import { useSnapshot } from './useSnapshot'
import type { PitchView, SessionView } from './replay'
import type { Snapshot } from './types'

function Race({ snap, tl }: { snap: Snapshot; tl: Timeline }) {
  const { view, days } = tl
  const data = useMemo(() => {
    const rows: Record<string, Record<string, number | string>> = Object.fromEntries(days.map(d => [d, { day: d }]))
    for (const p of view.pods) p.twr_series.forEach(([d, v]) => { rows[d][p.pod_id] = (v - 1) * 100 })
    const base = Number(snap.generated_from.initial_cash)
    view.benchSeries.forEach(([d, v]) => { rows[d].benchmark = (v / base - 1) * 100 })
    return days.map(d => rows[d])
  }, [snap, view, days])
  const dots = view.pitches.filter(p => p.entry).map(p => ({ p, y: data.find(r => r.day === p.entry!.session_day)?.[p.pod_id] as number | undefined })).filter(x => x.y !== undefined)
  return (
    <div className="glass p-3 sm:p-4">
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
            <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
            <XAxis dataKey="day" tickFormatter={dayLabel} tick={{ fill: '#94a3b8', fontSize: 11 }} minTickGap={36} />
            <YAxis tickFormatter={v => `${Number(v).toFixed(1)}%`} tick={{ fill: '#94a3b8', fontSize: 11 }} domain={['auto', 'auto']} />
            <Tooltip contentStyle={{ background: '#0f1726', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 12 }}
                     labelFormatter={l => dayLabel(String(l))} formatter={(v: number) => `${v.toFixed(2)}%`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine x={view.day} stroke="#67e8f9" strokeOpacity={0.6} />
            {view.pods.map(p => <Line key={p.pod_id} type="monotone" dataKey={p.pod_id} name={`${snap.pods.find(x => x.pod_id === p.pod_id)!.name} sleeve`} stroke={POD_HEX[p.pod_id]} strokeWidth={2.4} dot={false} isAnimationActive={false} connectNulls />)}
            <Line type="monotone" dataKey="benchmark" name="Hold the whole universe" stroke="#64748b" strokeDasharray="5 4" strokeWidth={1.6} dot={false} isAnimationActive={false} connectNulls />
            {dots.map(({ p, y }) => (
              <ReferenceDot key={p.proposal_id} x={p.entry!.session_day} y={y} r={4.5} fill={POD_HEX[p.pod_id]} stroke="#0b1220" strokeWidth={1.5}
                            ifOverflow="visible" style={{ cursor: 'pointer' }} onClick={() => tl.select(p.proposal_id)} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-slate-500">Each team is measured on what it earned, with capital transfers removed (time-weighted), drawn only up to the session you are viewing. Dots are fills: click one for its pitch. The dashed line holds an equal-weight basket of the same synthetic universe.</p>
    </div>
  )
}

function groupFeed(rows: PitchView[]) {
  // Repeat refusals of the same name for the same reason (a pending buyout, a too-small size) collapse into one line.
  const out: { key: string; rows: PitchView[] }[] = []
  const index = new Map<string, { key: string; rows: PitchView[] }>()
  for (const r of [...rows].reverse()) {
    const d = r.decision
    const repeatable = d && d.outcome === 'DECLINED' && !d.reasons.includes('D0_RANK_CAP')
    const key = repeatable ? `${r.pod_id}|${r.symbol}|${d.reasons.join('+')}` : r.proposal_id
    const g = index.get(key)
    if (g) { g.rows.push(r); continue }
    const ng = { key, rows: [r] }
    index.set(key, ng)
    out.push(ng)
  }
  return out
}

function ApexDesk({ snap, view, tl }: { snap: Snapshot; view: SessionView; tl: Timeline }) {
  const [filter, setFilter] = useState<'all' | 'funded' | 'declined'>('all')
  const [pod, setPod] = useState<string>('all')
  const [showAll, setShowAll] = useState(false)
  const rows = view.pitches.filter(r => (filter === 'all' || (filter === 'funded') === (r.decision?.outcome === 'FUNDED')) && (pod === 'all' || r.pod_id === pod))
  const all = groupFeed(rows)
  const groups = showAll ? all : all.slice(0, 8)
  const btn = (on: boolean) => `px-3 py-1 rounded-full text-sm border ${on ? 'border-cyan-300/60 bg-cyan-400/15 text-cyan-100' : 'border-slate-700 text-slate-400 hover:text-white'}`
  return (
    <div className="glass p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Filter pitches">
        {(['all', 'funded', 'declined'] as const).map(f => <button key={f} className={btn(filter === f)} onClick={() => setFilter(f)}>{f[0].toUpperCase() + f.slice(1)}</button>)}
        <span className="mx-1 w-px bg-slate-700" />
        <button className={btn(pod === 'all')} onClick={() => setPod('all')}>All teams</button>
        {view.pods.map(p => <button key={p.pod_id} className={btn(pod === p.pod_id)} onClick={() => setPod(p.pod_id)}>{podById(snap, p.pod_id).name}</button>)}
      </div>
      <ul className="divide-y divide-slate-800/80">
        {groups.length === 0 && <li className="py-6 text-center text-sm text-slate-500">No pitches yet at this point in the replay.</li>}
        {groups.map(g => {
          const r = g.rows[0]
          const first = g.rows[g.rows.length - 1]
          const p = podById(snap, r.pod_id)
          const d = r.decision
          return (
            <li key={g.key}>
              <button onClick={() => { tl.stop(); tl.select(r.proposal_id); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
                      className="block w-full rounded-lg px-1 py-3 text-left hover:bg-white/5">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="w-14 font-mono text-xs text-slate-500">{dayLabel(r.as_of_session)}</span>
                  <PodChip pod={p} />
                  <span className="font-mono font-bold text-white">{r.symbol}</span>
                  {d?.outcome === 'FUNDED' ? <span className="chip chip-funded">FUNDED</span> : <span className="chip chip-declined">DECLINED · {reasonLabel(d?.reasons ?? [])}</span>}
                  {r.state === 'OPEN' && <span className="chip chip-neutral">OPEN {usd(r.pnl, true)}</span>}
                  {r.state === 'CLOSED' && <span className={`chip ${Number(r.pnl) >= 0 ? 'chip-funded' : 'chip-declined'}`}>{usd(r.pnl, true)}</span>}
                  {r.state === 'QUEUED' && <span className="chip chip-neutral">QUEUED</span>}
                  {g.rows.length > 1 && <span className="chip chip-neutral">x{g.rows.length} · {dayLabel(first.as_of_session)} to {dayLabel(r.as_of_session)}</span>}
                </div>
                <p className="mt-1 line-clamp-1 text-sm text-slate-400">{r.packet.thesis}</p>
              </button>
            </li>
          )
        })}
      </ul>
      {all.length > 8 && (
        <button className="mt-2 w-full rounded-lg border border-slate-700 py-2 text-sm text-slate-300 hover:text-white" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show fewer' : `Show all ${all.length} pitches so far`}
        </button>
      )}
    </div>
  )
}

function Scoreboard({ snap, view }: { snap: Snapshot; view: SessionView }) {
  const rows = [...view.pods].sort((a, b) => a.rank - b.rank)
  const th = 'px-2 py-2 text-right text-[11px] uppercase tracking-wider text-slate-400 font-semibold'
  const td = 'px-2 py-2 text-right font-mono text-sm'
  return (
    <div className="glass overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <thead><tr className="border-b border-slate-800">
          <th className={`${th} text-left`}>Team</th><th className={th}>Return</th><th className={th}>Max drawdown</th><th className={th}>Volatility (ann.)</th>
          <th className={th} title="Mean daily return over daily standard deviation, annualised. Unstable over so few sessions.">Return / risk</th>
          <th className={th}>Win rate</th><th className={th}>Avg exposure</th><th className={th}>Trades</th>
        </tr></thead>
        <tbody>
          {rows.map(p => {
            const pod = podById(snap, p.pod_id)
            return (
              <tr key={p.pod_id} className="border-b border-slate-800/60 last:border-0">
                <td className="px-2 py-2 text-left"><Link to={`/team/${p.pod_id}?s=${view.index + 1}`} className="flex items-center gap-2"><span className="font-mono text-slate-500">#{p.rank}</span><PodChip pod={pod} /></Link></td>
                <td className={`${td} ${tone(p.return)}`}>{pct(p.return, 2)}</td>
                <td className={td}>{pct(p.max_drawdown, 1, false)}</td>
                <td className={td}>{pct(p.volatility_ann, 1, false)}</td>
                <td className={td}>{num(p.sharpe_like)}</td>
                <td className={td}>{pct(p.win_rate, 0, false)}</td>
                <td className={td}>{view.index === 0 ? '-' : pct(p.avg_exposure, 0, false)}</td>
                <td className={td}>{p.trades}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="px-3 py-2 text-xs text-slate-500">Ranked by return per unit of risk as of session {view.index + 1}. Sleeves are fixed, so a leader does not receive more capital. With {view.pods[0]?.sessions} synthetic sessions and a handful of trades this ordering demonstrates the accounting; it is not a skill estimate.</p>
    </div>
  )
}

function Sleeping({ snap }: { snap: Snapshot }) {
  const asleep = snap.pods.filter(p => p.status === 'INACTIVE')
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {asleep.map(p => (
        <Link key={p.pod_id} to={`/team/${p.pod_id}`} className="flex items-start gap-2.5 rounded-xl border border-slate-800 bg-slate-950/40 p-2.5 hover:border-slate-600" aria-label={`${p.name}, inactive`}>
          <PodShark pod={p} size={40} />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-300">{p.name}</div>
            <div className="text-[11px] leading-snug text-slate-500 line-clamp-3">{p.inactive_reason}</div>
          </div>
        </Link>
      ))}
    </div>
  )
}

export default function AquariumPage() {
  const { snap, error } = useSnapshot()
  if (!snap) return <Loading error={error} />
  return <Aquarium snap={snap} />
}

function Aquarium({ snap }: { snap: Snapshot }) {
  const tl = useTimeline(snap)
  const { view } = tl
  const pitchOf = (symbol: string, pod: string) => [...view.pitches].reverse().find(p => p.symbol === symbol && p.pod_id === pod && p.state === 'OPEN')
  const ok = snap.checks.every(c => c.ok)
  const pods = snap.pods.filter(p => p.status === 'ACTIVE')
  const [a, b] = pods
  const pv = (id: string) => view.pods.find(p => p.pod_id === id)!
  return (
    <>
      <div className="pt-1">
        <h1 className="text-2xl font-bold leading-tight text-white sm:text-4xl">Two sharks hunt. <span className="text-amber-300">One CIO decides.</span></h1>
        <p className="mt-1 text-sm text-slate-300 sm:hidden">Press play to replay 70 synthetic sessions.</p>
        <p className="mt-2 hidden max-w-3xl text-slate-300 sm:block">
          {a.name} and {b.name} each pitch trades to Apex, who funds or declines them by fixed rules while Risk watches every order. Press play to replay all {view.total} sessions of this
          synthetic competition, and pause on any decision.
        </p>
      </div>

      <TimelineBar tl={tl} />

      <div className="arena mt-4 p-3 sm:p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_1.35fr_1fr] lg:items-start">
          <div className="lg:order-2"><ApexColumn snap={snap} view={view} selected={tl.selected} onSelect={id => { tl.stop(); tl.select(id) }} /></div>
          <div className="lg:order-1"><Contender pod={a} pv={pv(a.pod_id)} rival={pv(b.pod_id)} view={view} pitchOf={pitchOf} onSelect={id => { tl.stop(); tl.select(id) }} /></div>
          <div className="lg:order-3"><Contender pod={b} pv={pv(b.pod_id)} rival={pv(a.pod_id)} view={view} pitchOf={pitchOf} onSelect={id => { tl.stop(); tl.select(id) }} /></div>
        </div>
        <div className="mt-4 border-t border-slate-800/80 pt-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Asleep in the deep · {snap.pods.length - pods.length} teams with no working strategy yet</div>
          <Sleeping snap={snap} />
        </div>
      </div>

      <Section id="capital-desk" title="Apex's capital desk" hint="Returns are earned by trading. Capital is awarded by Apex. They are never mixed.">
        <CapitalDesk snap={snap} tl={tl} />
      </Section>

      <Section title="The race" hint={`Each team's investment return, with transfers removed, through ${dayLabel(view.day)}`}>
        <Race snap={snap} tl={tl} />
      </Section>

      <Section title="Apex's desk" hint="Every pitch so far, newest first. Click one to put it in the spotlight.">
        <ApexDesk snap={snap} view={view} tl={tl} />
      </Section>

      <Section title="Scoreboard" hint="Risk-adjusted, from the ledger's end-of-session valuations">
        <Scoreboard snap={snap} view={view} />
      </Section>

      <Section title="How Apex decides">
        <div className="glass p-4 text-sm leading-relaxed text-slate-300">
          <p>{snap.apex.rule}</p>
          <p className="mt-2 text-amber-200/90"><strong>Capital follows evidence, in small steps.</strong> Every {snap.apex.capital_policy?.review_every} sessions (first at {snap.apex.capital_policy?.min_history}) Apex scores each team on its trailing return minus half its worst drawdown, with transfers removed. If one team leads by a clear margin and has shown it can use more capital, Apex moves one step ({Number(snap.apex.capital_policy?.step_pct ?? 0) * 100}% of the fund, about $500) to it, taking the trailing team's uncommitted cash first and the central reserve for the rest. It never sells a position to do it, never touches cash promised to an order, and holds when the race is too close, the data is untrusted or no one is making money. These are starting rules, not tuned parameters.</p>
          <p className="mt-2 text-slate-400">
            Limits enforced by the Risk Engine: {snap.limits.position_cap_pct}% max per position, {snap.limits.risk_per_trade_pct}% of NAV at risk per trade,
            {' '}{snap.limits.max_invested_pct}% max invested, {snap.limits.daily_loss_pause_pct}% daily-loss pause, {snap.limits.drawdown_pause_pct}% drawdown pause.
            Apex here is deterministic (D0): no language model is called and nothing costs money.
          </p>
          <p className="mt-2 text-xs text-slate-500">Decline reasons seen: {Array.from(new Set(snap.proposals.flatMap(r => r.decision?.reasons ?? []))).map(c => reasonLabel([c])).join(', ')}.</p>
          <p className="mt-3 text-sm">
            Every figure on this page is rebuilt in your browser from the ledger events up to the session you are viewing: nothing later is read.{' '}
            <Link to="/lab" className="text-cyan-300 hover:underline">{ok ? 'Ledger verified' : 'Ledger check FAILED'}: inspect the evidence in the Research Lab.</Link>
          </p>
        </div>
      </Section>
    </>
  )
}
