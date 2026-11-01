import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import PodShark, { POD_HEX } from './PodShark'
import { DecisionChip, Loading, PodChip, ResultChip, Section, Stat, podById } from './ui'
import { dayLabel, num, pct, reasonLabel, tone, usd } from './format'
import { useSnapshot } from './useSnapshot'
import type { Pod, ProposalRow, Snapshot } from './types'

function Sparkline({ series, color }: { series: [string, string][]; color: string }) {
  const vals = series.map(s => Number(s[1]))
  if (vals.length < 2) return null
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * 100},${28 - ((v - min) / span) * 26}`).join(' ')
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="w-full h-8" aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function PodCard({ pod }: { pod: Pod }) {
  const active = pod.status === 'ACTIVE'
  const hex = POD_HEX[pod.pod_id]
  return (
    <Link to={`/team/${pod.pod_id}`} className="glass glass-hover block p-4" style={{ borderColor: active ? `${hex}55` : undefined }}
          aria-label={`${pod.name} pod, ${active ? 'active' : 'inactive'}`}>
      <div className="flex items-start gap-3">
        <PodShark pod={pod} size={64} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-bold text-white">{pod.name}</h3>
            {active
              ? <span className="chip chip-funded">ACTIVE · #{pod.rank}</span>
              : <span className="chip chip-neutral">INACTIVE</span>}
          </div>
          <p className="text-sm" style={{ color: hex }}>{pod.tagline}</p>
          <p className="mt-1 text-xs text-slate-400 leading-snug">{pod.mandate}</p>
        </div>
      </div>
      {active ? (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
            <div><div className="text-[10px] uppercase tracking-wider text-slate-500">Sleeve NAV</div><div className="font-mono font-semibold text-white">{usd(pod.nav)}</div></div>
            <div><div className="text-[10px] uppercase tracking-wider text-slate-500">Return</div><div className={`font-mono font-semibold ${tone(pod.return)}`}>{pct(pod.return, 2)}</div></div>
            <div><div className="text-[10px] uppercase tracking-wider text-slate-500">Max DD</div><div className="font-mono font-semibold text-slate-200">{pct(pod.max_drawdown, 1, false)}</div></div>
          </div>
          <div className="mt-2"><Sparkline series={pod.nav_series ?? []} color={hex} /></div>
          <div className="mt-1 text-xs text-slate-400">{pod.proposals} proposals · {pod.funded_proposals} funded · {pod.trades} closed trades</div>
        </>
      ) : (
        <div className="mt-3 rounded-lg border border-slate-700/60 bg-slate-900/50 p-2.5 text-xs text-slate-400">
          <span className="font-semibold text-slate-300">Not hunting yet.</span> {pod.inactive_reason} No capital, no trades, no performance.
        </div>
      )}
    </Link>
  )
}

function Race({ snap }: { snap: Snapshot }) {
  const data = useMemo(() => {
    const rows: Record<string, Record<string, number | string>> = {}
    const add = (key: string, series: [string, string][], base: number) =>
      series.forEach(([d, v]) => { (rows[d] ??= { day: d })[key] = (Number(v) / base - 1) * 100 })
    for (const p of snap.pods) if (p.status === 'ACTIVE') add(p.pod_id, p.nav_series!, Number(p.funded))
    add('benchmark', snap.fund.benchmark.series, Number(snap.generated_from.initial_cash))
    return Object.values(rows).sort((a, b) => String(a.day).localeCompare(String(b.day)))
  }, [snap])
  const active = snap.pods.filter(p => p.status === 'ACTIVE')
  return (
    <div className="glass p-3 sm:p-4">
      <div style={{ width: '100%', height: 280 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
            <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
            <XAxis dataKey="day" tickFormatter={dayLabel} tick={{ fill: '#94a3b8', fontSize: 11 }} minTickGap={36} />
            <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#94a3b8', fontSize: 11 }} domain={['auto', 'auto']} />
            <Tooltip contentStyle={{ background: '#0f1726', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 12 }}
                     labelFormatter={l => dayLabel(String(l))} formatter={(v: number) => `${v.toFixed(2)}%`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {active.map(p => <Line key={p.pod_id} type="monotone" dataKey={p.pod_id} name={`${p.name} sleeve`} stroke={POD_HEX[p.pod_id]} strokeWidth={2.4} dot={false} />)}
            <Line type="monotone" dataKey="benchmark" name="Universe buy-and-hold" stroke="#64748b" strokeDasharray="5 4" strokeWidth={1.6} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-slate-500">Each sleeve is measured on its own funded capital; the dashed line is an equal-weight hold of the same fixture universe on $10,000. Synthetic prices.</p>
    </div>
  )
}

interface Group { key: string; rows: ProposalRow[] }

function groupFeed(rows: ProposalRow[]): Group[] {
  // Repeat refusals of the same name for the same reason (a pending buyout, a too-small size) collapse into one line.
  const out: Group[] = []
  const index = new Map<string, Group>()
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

function ApexDesk({ snap }: { snap: Snapshot }) {
  const [filter, setFilter] = useState<'all' | 'funded' | 'declined'>('all')
  const [pod, setPod] = useState<string>('all')
  const rows = snap.proposals.filter(r =>
    (filter === 'all' || (filter === 'funded') === (r.decision?.outcome === 'FUNDED')) && (pod === 'all' || r.pod_id === pod))
  const [showAll, setShowAll] = useState(false)
  const all = groupFeed(rows)
  const groups = showAll ? all : all.slice(0, 10)
  const activePods = snap.pods.filter(p => p.status === 'ACTIVE')
  const btn = (on: boolean) => `px-3 py-1 rounded-full text-sm border ${on ? 'border-cyan-300/60 bg-cyan-400/15 text-cyan-100' : 'border-slate-700 text-slate-400 hover:text-white'}`
  return (
    <div className="glass p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Filter proposals">
        {(['all', 'funded', 'declined'] as const).map(f => <button key={f} className={btn(filter === f)} onClick={() => setFilter(f)}>{f[0].toUpperCase() + f.slice(1)}</button>)}
        <span className="mx-1 w-px bg-slate-700" />
        <button className={btn(pod === 'all')} onClick={() => setPod('all')}>All pods</button>
        {activePods.map(p => <button key={p.pod_id} className={btn(pod === p.pod_id)} onClick={() => setPod(p.pod_id)}>{p.name}</button>)}
      </div>
      <ul className="divide-y divide-slate-800/80">
        {groups.length === 0 && <li className="py-6 text-center text-sm text-slate-500">No proposals match.</li>}
        {groups.map(g => {
          const r = g.rows[0] // newest first
          const first = g.rows[g.rows.length - 1]
          const p = podById(snap, r.pod_id)
          return (
            <li key={g.key}>
              <Link to={`/proposal/${encodeURIComponent(r.proposal_id)}`} className="block py-3 px-1 hover:bg-white/5 rounded-lg">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="font-mono text-xs text-slate-500 w-14">{dayLabel(r.as_of_session)}</span>
                  <PodChip pod={p} />
                  <span className="font-mono font-bold text-white">{r.symbol}</span>
                  <DecisionChip row={r} />
                  <ResultChip row={r} />
                  {g.rows.length > 1 && <span className="chip chip-neutral">x{g.rows.length} · {dayLabel(first.as_of_session)} to {dayLabel(r.as_of_session)}</span>}
                </div>
                <p className="mt-1 text-sm text-slate-400 line-clamp-1">{r.packet.thesis}</p>
              </Link>
            </li>
          )
        })}
      </ul>
      {all.length > 10 && (
        <button className="mt-2 w-full rounded-lg border border-slate-700 py-2 text-sm text-slate-300 hover:text-white" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show fewer' : `Show all ${all.length} pitches`}
        </button>
      )}
    </div>
  )
}

function Scoreboard({ snap }: { snap: Snapshot }) {
  const rows = snap.pods.filter(p => p.status === 'ACTIVE').sort((a, b) => a.rank! - b.rank!)
  const th = 'px-2 py-2 text-right text-[11px] uppercase tracking-wider text-slate-400 font-semibold'
  const td = 'px-2 py-2 text-right font-mono text-sm'
  return (
    <div className="glass overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <thead><tr className="border-b border-slate-800">
          <th className={`${th} text-left`}>Pod</th><th className={th}>Return</th><th className={th}>Max drawdown</th><th className={th}>Volatility (ann.)</th>
          <th className={th} title="Mean daily return over daily standard deviation, annualised. 70 sessions of synthetic data: indicative only.">Return / risk</th>
          <th className={th}>Win rate</th><th className={th}>Avg exposure</th><th className={th}>Trades</th>
        </tr></thead>
        <tbody>
          {rows.map(p => (
            <tr key={p.pod_id} className="border-b border-slate-800/60 last:border-0">
              <td className="px-2 py-2 text-left"><Link to={`/team/${p.pod_id}`} className="flex items-center gap-2"><span className="font-mono text-slate-500">#{p.rank}</span><PodChip pod={p} /></Link></td>
              <td className={`${td} ${tone(p.return)}`}>{pct(p.return, 2)}</td>
              <td className={td}>{pct(p.max_drawdown, 1, false)}</td>
              <td className={td}>{pct(p.volatility_ann, 1, false)}</td>
              <td className={td}>{num(p.sharpe_like)}</td>
              <td className={td}>{pct(p.win_rate, 0, false)}</td>
              <td className={td}>{pct(p.avg_exposure, 0, false)}</td>
              <td className={td}>{p.trades}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 text-xs text-slate-500">Ranked by return per unit of risk. Sleeves are fixed, so a leader does not receive more capital. Over {rows[0]?.sessions} synthetic sessions with a handful of trades this ordering is a demonstration of the accounting, not a skill estimate.</p>
    </div>
  )
}

export default function AquariumPage() {
  const { snap, error } = useSnapshot()
  if (!snap) return <Loading error={error} />
  const funded = snap.proposals.filter(p => p.decision?.outcome === 'FUNDED').length
  const lastDecline = snap.proposals.filter(p => p.decision?.outcome === 'DECLINED').length
  const active = snap.pods.filter(p => p.status === 'ACTIVE')
  const ok = snap.checks.every(c => c.ok)
  const lead = [...active].sort((a, b) => a.rank! - b.rank!)[0]
  return (
    <>
      <div className="pt-2">
        <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight">Six sharks. One CIO. <span className="text-cyan-300">One tank.</span></h1>
        <p className="mt-2 max-w-3xl text-slate-300">
          Independent teams pitch trades to Apex, the capital allocator. Apex funds or declines each pitch by fixed rules, Risk watches every order,
          and each team's sleeve keeps its own books. Two teams are hunting in this demonstration; four are honestly asleep.
        </p>
      </div>

      <div className="mt-5 grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Fund NAV" value={usd(snap.fund.nav)} sub={<><span className={tone(snap.fund.return)}>{pct(snap.fund.return, 2)}</span> on {usd(snap.generated_from.initial_cash)}</>} />
        <Stat label="Teams hunting" value={`${active.length} of ${snap.pods.length}`} sub={lead ? `${lead.name} leads` : undefined} />
        <Stat label="Pitches to Apex" value={snap.proposals.length} sub={`${funded} funded · ${lastDecline} declined`} />
        <Link to="/lab" className="block"><Stat label="Ledger" value={<span className={ok ? 'text-gain' : 'text-loss'}>{ok ? 'Verified' : 'FAILED'}</span>} sub={`${snap.generated_from.events} events · open the Research Lab`} /></Link>
      </div>

      <div className="glass mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm" style={{ borderColor: 'rgba(245,158,11,0.35)' }}>
        <span className="chip chip-warn">FIXED SLEEVES</span>
        <span className="text-slate-300">
          Apex gives each hunting pod a fixed share of the fund ({active.map(p => `${p.name} ${Number(p.sleeve_weight) * 100}%`).join(', ')}; {Number(snap.apex.unallocated_weight) * 100}% stays in cash).
          It decides which <em>pitches</em> to fund inside a sleeve, not which <em>shark</em> deserves more of the fund. Capital competition between pods is the next milestone.
        </span>
      </div>

      <Section title="The tank" hint="Click a team for its mandate, research desk, books and pitches.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{snap.pods.map(p => <PodCard key={p.pod_id} pod={p} />)}</div>
      </Section>

      <Section title="The race" hint="Each team's return on its own fixed sleeve">
        <Race snap={snap} />
      </Section>

      <Section title="Apex's desk" hint="Every pitch, newest first. Click one to follow it from research to result.">
        <ApexDesk snap={snap} />
      </Section>

      <Section title="Scoreboard" hint="Risk-adjusted, from the ledger's end-of-session valuations">
        <Scoreboard snap={snap} />
      </Section>

      <Section title="How Apex decides">
        <div className="glass p-4 text-sm text-slate-300 leading-relaxed">
          <p>{snap.apex.rule}</p>
          <p className="mt-2 text-amber-200/90"><strong>Allocation today is fixed, not competitive.</strong> The 30/30 sleeve weights are set at the start and never change; better performance earns a pod no extra capital and worse performance costs it none. Dynamic, performance-driven allocation is a later milestone.</p>
          <p className="mt-2 text-slate-400">
            Limits enforced by the Risk Engine: {snap.limits.position_cap_pct}% max per position, {snap.limits.risk_per_trade_pct}% of NAV at risk per trade,
            {' '}{snap.limits.max_invested_pct}% max invested, {snap.limits.daily_loss_pause_pct}% daily-loss pause, {snap.limits.drawdown_pause_pct}% drawdown pause.
            Apex here is deterministic (D0): no language model is called and nothing costs money.
          </p>
          <p className="mt-2 text-xs text-slate-500">Decline reasons seen: {Array.from(new Set(snap.proposals.flatMap(r => r.decision?.reasons ?? []))).map(c => reasonLabel([c])).join(', ')}.</p>
        </div>
      </Section>
    </>
  )
}
