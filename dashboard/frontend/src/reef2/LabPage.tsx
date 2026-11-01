import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Loading, Section } from './ui'
import { dayLabel, num, pct, usd } from './format'
import { useSnapshot } from './useSnapshot'
import { recomputePods, verifyIntegrity } from './verify'
import type { IntegrityReport } from './verify'
import type { LedgerEventJson, Snapshot } from './types'

function Check({ ok, title, detail }: { ok: boolean | null; title: string; detail: string }) {
  return (
    <li className="flex gap-3 py-2.5">
      <span className={`mt-0.5 w-5 text-center font-bold ${ok === null ? 'text-slate-500' : ok ? 'text-gain' : 'text-loss'}`}>{ok === null ? '…' : ok ? '✓' : '✗'}</span>
      <div className="min-w-0"><div className="font-semibold text-slate-100">{title}</div><div className="text-sm text-slate-400 break-words">{detail}</div></div>
    </li>
  )
}

function Verification({ snap }: { snap: Snapshot }) {
  const [report, setReport] = useState<IntegrityReport | null>(null)
  const [checkpoint, setCheckpoint] = useState('')
  const header = useMemo(() => ({ events: snap.generated_from.events, head_hash: snap.generated_from.head_hash }), [snap])
  useEffect(() => {
    verifyIntegrity(snap.events, header, checkpoint)
      .then(setReport)
      .catch(() => setReport({ ok: false, checks: [{ name: 'Verification could not run', ok: false, detail: 'this browser does not expose Web Crypto here' }], firstBadSeq: null, head: '', count: 0 }))
  }, [snap, header, checkpoint])
  const pods = useMemo(() => recomputePods(snap), [snap])
  return (
    <div className="glass p-4">
      <p className="mb-1 text-sm text-slate-400">Run now, in your browser, from the raw events on this page. Nothing below is read from the engine's own summary.</p>
      <ul className="divide-y divide-slate-800/70">
        {report ? report.checks.map(c => <Check key={c.name} ok={c.ok} title={c.name} detail={c.detail} />) : <Check ok={null} title="Integrity checks" detail="running..." />}
        {pods.map(p => (
          <Check key={p.pod_id} ok={p.ok} title={`${snap.pods.find(x => x.pod_id === p.pod_id)!.name} sleeve: books recomputed from funding events and fills`}
                 detail={`cash ${usd(p.cash)} + positions at the last official closes = NAV ${usd(p.nav)}; page claims ${usd(p.claimedNav)}. Realized P&L ${usd(p.realized, true)} (average-cost).`} />
        ))}
        {snap.checks.map(c => <Check key={c.name} ok={c.ok} title={`Engine: ${c.name}`} detail={c.detail} />)}
      </ul>
      <div className="mt-3 rounded-lg border border-amber-400/30 bg-amber-400/5 p-3 text-sm text-slate-300">
        <p><strong className="text-amber-300">What this proves, and what it does not.</strong> The checks above are self-contained: they catch a changed, missing, reordered or
          cut-off event, because the events, their hash chain and the header must all agree. They cannot catch a snapshot that was <em>entirely rewritten</em> with the hashes
          and header recomputed to match. Only a head hash recorded somewhere independent can. The head for this snapshot is
          {' '}<code className="break-all font-mono text-cyan-300">{snap.generated_from.head_hash}</code>; the snapshot is also rebuilt from fixed seeds by
          {' '}<code className="font-mono text-cyan-300">tools/build_competition_snapshot.py</code> and compared in a test.</p>
        <label className="mt-2 block text-xs text-slate-400">Compare with a head hash you recorded independently
          <input value={checkpoint} onChange={e => setCheckpoint(e.target.value)} placeholder="paste a 64-character head hash"
                 className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-xs text-slate-200" spellCheck={false} />
        </label>
      </div>
    </div>
  )
}

function Formulas({ snap }: { snap: Snapshot }) {
  const pods = snap.pods.filter(p => p.status === 'ACTIVE')
  const th = 'px-2 py-2 text-right text-[11px] uppercase tracking-wider text-slate-400'
  return (
    <div className="glass overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead><tr className="border-b border-slate-800"><th className={`${th} text-left`}>Pod</th><th className={th}>Funded</th><th className={th}>Realized</th><th className={th}>Unrealized</th><th className={th}>= NAV</th><th className={th}>Return</th><th className={th}>Max DD</th><th className={th}>Vol (ann.)</th><th className={th}>Return/risk</th></tr></thead>
        <tbody>
          {pods.map(p => (
            <tr key={p.pod_id} className="border-b border-slate-800/60 last:border-0 font-mono">
              <td className="px-2 py-2 text-left font-sans font-semibold text-white">{p.name}</td>
              <td className="px-2 py-2 text-right">{usd(p.funded)}</td><td className="px-2 py-2 text-right">{usd(p.realized_pnl, true)}</td>
              <td className="px-2 py-2 text-right">{usd(p.unrealized_pnl, true)}</td><td className="px-2 py-2 text-right text-white">{usd(p.nav)}</td>
              <td className="px-2 py-2 text-right">{pct(p.return, 3)}</td><td className="px-2 py-2 text-right">{pct(p.max_drawdown, 2, false)}</td>
              <td className="px-2 py-2 text-right">{pct(p.volatility_ann, 1, false)}</td><td className="px-2 py-2 text-right">{num(p.sharpe_like)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="grid gap-2 border-t border-slate-800 px-3 py-3 text-xs text-slate-400 sm:grid-cols-2">
        <div><dt className="font-semibold text-slate-300">Return</dt><dd>sleeve NAV at the last session / funded capital − 1</dd></div>
        <div><dt className="font-semibold text-slate-300">Max drawdown</dt><dd>worst fall of daily sleeve NAV from its running peak</dd></div>
        <div><dt className="font-semibold text-slate-300">Volatility (ann.)</dt><dd>sample standard deviation of daily sleeve returns × √252</dd></div>
        <div><dt className="font-semibold text-slate-300">Return / risk</dt><dd>mean daily return ÷ daily standard deviation × √252; unstable over this few sessions</dd></div>
        <div><dt className="font-semibold text-slate-300">NAV</dt><dd>sleeve cash + shares × official close; a holding without a valid close is carried at cost and blocks new buys</dd></div>
        <div><dt className="font-semibold text-slate-300">Realized P&L</dt><dd>sale proceeds − average cost of the shares sold; no fees or slippage in this demonstration</dd></div>
      </dl>
    </div>
  )
}

function Explorer({ snap }: { snap: Snapshot }) {
  const [params, setParams] = useSearchParams()
  const focus = Number(params.get('seq')) || null
  const [kind, setKind] = useState('all')
  const [pod, setPod] = useState('all')
  const kinds = Array.from(new Set(snap.events.map(e => e.kind))).sort()
  const rows = snap.events.filter(e =>
    (kind === 'all' || e.kind === kind) &&
    (pod === 'all' || (e.payload as { sleeve_id?: string }).sleeve_id === pod || (focus !== null && e.seq === focus)))
  const [open, setOpen] = useState<number | null>(focus)
  useEffect(() => {
    if (focus) {
      setOpen(focus)
      document.getElementById(`ev-${focus}`)?.scrollIntoView({ block: 'center' })
    }
  }, [focus, snap])
  const sel = 'rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200'
  const summarize = (e: LedgerEventJson): string => {
    const p = e.payload as Record<string, any>
    switch (e.kind) {
      case 'FILL': return `${p.sleeve_id} ${p.side} ${p.shares} ${p.symbol} @ ${p.price}`
      case 'PROPOSAL_SUBMITTED': return `${p.pod_id} pitches ${p.symbol}: ask ${usd(p.capital_request.dollars)}`
      case 'APEX_DECISION': return `${p.sleeve_id} ${p.symbol ?? String(p.proposal_id).split(':')[2]}: ${p.outcome}${p.reasons?.length ? ' (' + p.reasons.join(', ') + ')' : ''}`
      case 'ORDER_QUEUED': return `${p.sleeve_id} ${p.intent} up to ${p.requested_shares} ${p.symbol}, fills ${p.fill_session}`
      case 'ORDER_REJECTED': return `${p.sleeve_id} ${p.symbol ?? ''} ${p.stage}: ${p.code}`
      case 'STOP_UPDATED': return `${p.sleeve_id} ${p.symbol} stop → ${p.stop_price}`
      case 'SESSION_MARKED': return `${p.session_day}: fund NAV ${usd(p.nav)}`
      case 'SESSION_CLOSED': return `${p.session_day} closed`
      case 'SLEEVE_FUNDED': return `${p.sleeve_id} funded ${usd(p.amount)}`
      case 'SLEEVE_CREATED': return `${p.sleeve_id} created`
      case 'EPOCH_OPENED': return `epoch opened with ${usd(p.initial_cash)}`
      default: return ''
    }
  }
  return (
    <div className="glass p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap gap-2">
        <label className="text-sm text-slate-400">Kind <select className={sel} value={kind} onChange={e => setKind(e.target.value)}><option value="all">all</option>{kinds.map(k => <option key={k}>{k}</option>)}</select></label>
        <label className="text-sm text-slate-400">Pod <select className={sel} value={pod} onChange={e => setPod(e.target.value)}><option value="all">all</option>{snap.pods.filter(p => p.status === 'ACTIVE').map(p => <option key={p.pod_id} value={p.pod_id}>{p.name}</option>)}</select></label>
        <span className="ml-auto self-center text-xs text-slate-500">{rows.length} of {snap.events.length} events</span>
      </div>
      <ol className="max-h-[560px] overflow-y-auto text-sm">
        {rows.map(e => (
          <li key={e.seq} id={`ev-${e.seq}`} className={`border-b border-slate-800/60 ${focus === e.seq ? 'bg-cyan-400/10' : ''}`}>
            <button className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-0.5 px-1 py-2 text-left hover:bg-white/5"
                    onClick={() => { setOpen(open === e.seq ? null : e.seq); if (focus) setParams({}) }} aria-expanded={open === e.seq}>
              <span className="w-12 font-mono text-xs text-slate-500">#{e.seq}</span>
              <span className="chip chip-neutral">{e.kind}</span>
              <span className="min-w-0 flex-1 text-slate-300">{summarize(e)}</span>
              <span className="font-mono text-xs text-slate-500">{dayLabel(e.occurred_at.slice(0, 10))}</span>
            </button>
            {open === e.seq && (
              <div className="mb-2 rounded-lg bg-slate-950/70 p-3 text-xs">
                <div className="font-mono text-slate-400 break-all">hash {e.hash}<br />prev {e.prev_hash}<br />id {e.event_id} · {e.occurred_at}</div>
                <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-slate-300">{JSON.stringify(e.payload, null, 2)}</pre>
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

export default function LabPage() {
  const { snap, error } = useSnapshot()
  if (!snap) return <Loading error={error} />
  const g = snap.generated_from
  return (
    <>
      <div className="pt-2">
        <h1 className="text-3xl font-bold text-white">Research Lab</h1>
        <p className="mt-2 max-w-3xl text-slate-300">Where every number on the aquarium can be checked. The engine wrote {g.events} ledger events; this page re-verifies them and recomputes the books without trusting the engine's summary.</p>
        <p className="mt-1 text-sm text-slate-500">Epoch <span className="font-mono">{g.epoch_id}</span> · sessions {dayLabel(g.first_session)} to {dayLabel(g.last_session)} · head <span className="font-mono">{g.head_hash.slice(0, 16)}...</span></p>
      </div>
      <Section title="Verification"><Verification snap={snap} /></Section>
      <Section title="Performance figures and their formulas"><Formulas snap={snap} /></Section>
      <Section title="Ledger explorer" hint="Open any event; links from the proposal stories land here"><Explorer snap={snap} /></Section>
      <Section title="Provenance and limits">
        <div className="glass p-4 text-sm text-slate-300 leading-relaxed">
          <ul className="list-disc space-y-1.5 pl-5">
            <li><strong>Prices are synthetic.</strong> A seeded generator makes every bar (tests/fixtures/competition_scenario.py); reruns are byte-identical. No market data, no vendor, no cost.</li>
            <li><strong>The accounting is real.</strong> Orders, fills, stops, sleeves, risk checks and valuations come from the same engine and ledger Reef 2.0 would use. Fills are at the next open or the stop price, with no fees or slippage here.</li>
            <li><strong>Apex is deterministic and the sleeves are fixed.</strong> {snap.apex.rule} Apex does not yet move capital between pods based on performance.</li>
            <li><strong>Four pods are inactive</strong> and show no figures. Two active pods over {snap.pods.find(p => p.status === 'ACTIVE')?.sessions} sessions cannot say which philosophy is better.</li>
            <li><strong>Not live.</strong> No broker, no database writes, no model calls. Regenerate with <code className="font-mono text-cyan-300">uv run python tools/build_competition_snapshot.py</code>.</li>
          </ul>
          <p className="mt-3"><Link className="text-cyan-300 hover:underline" to="/">← Back to the aquarium</Link></p>
        </div>
      </Section>
    </>
  )
}
