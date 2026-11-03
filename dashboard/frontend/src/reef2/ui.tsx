import type { ReactNode } from 'react'
import type { Pod, ProposalRow, Snapshot } from './types'
import { POD_HEX } from './PodShark'
import { reasonLabel, usd, tone } from './format'
import { IS_LIVE } from './useSnapshot'

export function Section({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="mt-8">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-xl font-bold text-white">{title}</h2>
        {hint && <p className="text-sm text-slate-400">{hint}</p>}
      </div>
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, valueClass = 'text-white' }: { label: string; value: ReactNode; sub?: ReactNode; valueClass?: string }) {
  return (
    <div className="glass px-4 py-3 min-w-0">
      <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold font-mono ${valueClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-400">{sub}</div>}
    </div>
  )
}

export function PodChip({ pod }: { pod: Pod }) {
  return (
    <span className="chip" style={{ color: POD_HEX[pod.pod_id], background: `${POD_HEX[pod.pod_id]}1a`, borderColor: `${POD_HEX[pod.pod_id]}55` }}>
      {pod.name}
    </span>
  )
}

export function DecisionChip({ row }: { row: ProposalRow }) {
  const d = row.decision
  if (!d) return <span className="chip chip-neutral">PENDING</span>
  return d.outcome === 'FUNDED'
    ? <span className="chip chip-funded">FUNDED</span>
    : <span className="chip chip-declined" title={d.detail}>DECLINED · {reasonLabel(d.reasons)}</span>
}

export function ResultChip({ row }: { row: ProposalRow }) {
  const l = row.lifecycle
  if (!l || !l.entry) return null
  if (l.status === 'OPEN') return <span className={`chip chip-neutral`}>OPEN {usd(l.pnl, true)}</span>
  return <span className={`chip ${Number(l.pnl) >= 0 ? 'chip-funded' : 'chip-declined'}`}>{usd(l.pnl, true)}</span>
}

export const podById = (snap: Snapshot, id: string): Pod => snap.pods.find(p => p.pod_id === id)!

export function Loading({ error }: { error: string | null }) {
  return (
    <div className="glass mt-10 p-8 text-center text-slate-300">
      {error
        ? IS_LIVE
          ? <>No live-paper epoch is published here yet ({error}). It appears after <code className="font-mono text-cyan-300">uv run --group data python tools/live.py run</code> has processed a session. Activation is a separate, approved step.</>
          : <>Could not load the competition snapshot ({error}). Run <code className="font-mono text-cyan-300">uv run python tools/build_competition_snapshot.py</code> and reload.</>
        : 'Loading the tank...'}
    </div>
  )
}

export function Signed({ v, children }: { v: number | string | null | undefined; children: ReactNode }) {
  return <span className={tone(v)}>{children}</span>
}
