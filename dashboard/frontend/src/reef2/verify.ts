// Browser-side checks of the snapshot's own events. No server involved: given the events, anyone can
// recompute the hash chain and the headline numbers and compare them with what the page claims.
import type { LedgerEventJson, Snapshot } from './types.ts'

const GENESIS = '0'.repeat(64)

// Mirrors the Python canonical form: sorted keys, compact separators, ASCII only (\uXXXX escapes).
export function canonical(v: unknown): string {
  if (v === null || typeof v !== 'object') {
    const s = JSON.stringify(v)
    return s.replace(/[\u007f-￿]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'))
  }
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']'
  const o = v as Record<string, unknown>
  return '{' + Object.keys(o).sort().map(k => canonical(k) + ':' + canonical(o[k])).join(',') + '}'
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

export interface IntegrityCheck { name: string; ok: boolean; detail: string }
export interface IntegrityReport { ok: boolean; checks: IntegrityCheck[]; firstBadSeq: number | null; head: string; count: number }
export interface Header { events: number; head_hash: string }

// Self-contained integrity check of an event list against the header the same file carries. It detects altered,
// omitted, reordered and truncated events. It cannot detect a snapshot that was fully rewritten (events, hashes and
// header recomputed together); only a head hash recorded somewhere else can. Pass that as `expectedHead`.
export async function verifyIntegrity(events: LedgerEventJson[], header: Header, expectedHead?: string): Promise<IntegrityReport> {
  let firstBad: number | null = null
  const note = (seq: number) => { if (firstBad === null || seq < firstBad) firstBad = seq }

  let seqBad: number | null = null
  events.forEach((e, i) => { if (seqBad === null && e.seq !== i + 1) seqBad = e.seq })
  if (seqBad !== null) note(seqBad)

  let prev = GENESIS
  let linkBad: number | null = null
  let hashBad: number | null = null
  for (const e of events) {
    if (linkBad === null && e.prev_hash !== prev) linkBad = e.seq
    const content = { event_id: e.event_id, epoch_id: e.epoch_id, kind: e.kind, occurred_at: e.occurred_at, payload: e.payload }
    const expected = await sha256(`${e.seq}|${e.prev_hash}|${await sha256(canonical(content))}`)
    if (hashBad === null && e.hash !== expected) hashBad = e.seq
    prev = e.hash
  }
  if (linkBad !== null) note(linkBad)
  if (hashBad !== null) note(hashBad)
  const head = events.length ? events[events.length - 1].hash : GENESIS
  const countOk = events.length === header.events
  const headOk = head === header.head_hash
  const checks: IntegrityCheck[] = [
    { name: 'Sequence numbers are consecutive from 1', ok: seqBad === null,
      detail: seqBad === null ? `#1 to #${events.length}, no gaps, repeats or reordering` : `breaks at event #${seqBad}: an event is missing, repeated or out of order` },
    { name: 'Hash-chain continuity: each event points at the hash before it', ok: linkBad === null,
      detail: linkBad === null ? 'every prev_hash equals the hash of the event before it' : `broken at event #${linkBad}` },
    { name: 'Each event hash recomputes from its own content', ok: hashBad === null,
      detail: hashBad === null ? `${events.length} SHA-256 hashes recomputed in this browser` : `event #${hashBad} was altered after it was hashed` },
    { name: 'Event count matches the snapshot header', ok: countOk,
      detail: countOk ? `${events.length} events` : `header says ${header.events}, found ${events.length}${events.length < header.events ? ' (truncated)' : ''}` },
    { name: 'Final head hash matches the snapshot header', ok: headOk,
      detail: headOk ? `${head.slice(0, 20)}...` : `header ${header.head_hash.slice(0, 16)}... but the events end at ${head.slice(0, 16)}...` },
  ]
  if (expectedHead !== undefined && expectedHead.trim() !== '') {
    const ok = head === expectedHead.trim().toLowerCase()
    checks.push({ name: 'Head hash matches the independent checkpoint you entered', ok,
                  detail: ok ? 'equal' : `the checkpoint is ${expectedHead.trim().slice(0, 16)}... but the events end at ${head.slice(0, 16)}...` })
  }
  return { ok: checks.every(c => c.ok), checks, firstBadSeq: firstBad, head, count: events.length }
}

export interface PodRecompute { pod_id: string; funded: number; realized: number; cash: number; nav: number; claimedNav: number; ok: boolean }

// Average-cost accounting from the raw fills and funding events, plus the last official closes from SESSION_MARKED.
export function recomputePods(snap: Snapshot): PodRecompute[] {
  const cash: Record<string, number> = {}
  const funded: Record<string, number> = {}
  const realized: Record<string, number> = {}
  const book: Record<string, Record<string, { shares: number; cost: number }>> = {}
  let marks: Record<string, string> = {}
  for (const e of snap.events) {
    const p = e.payload as Record<string, any>
    if (e.kind === 'SLEEVE_FUNDED') {
      cash[p.sleeve_id] = (cash[p.sleeve_id] ?? 0) + Number(p.amount)
      funded[p.sleeve_id] = (funded[p.sleeve_id] ?? 0) + Number(p.amount)
    } else if (e.kind === 'FILL') {
      const sid: string = p.sleeve_id
      const sleeve = (book[sid] ??= {})
      const pos = (sleeve[p.symbol] ??= { shares: 0, cost: 0 })
      const px = Number(p.price), n = Number(p.shares)
      if (p.side === 'BUY') {
        pos.shares += n; pos.cost += px * n; cash[sid] -= px * n
      } else {
        const removed = pos.cost * n / pos.shares
        realized[sid] = (realized[sid] ?? 0) + px * n - removed
        pos.shares -= n; pos.cost -= removed; cash[sid] += px * n
      }
    } else if (e.kind === 'SESSION_MARKED') {
      marks = p.marks as Record<string, string>
    }
  }
  return snap.pods.filter(x => x.status === 'ACTIVE').map(pod => {
    const id = pod.pod_id
    let nav = cash[id] ?? 0
    for (const [sym, pos] of Object.entries(book[id] ?? {})) if (pos.shares > 0) nav += pos.shares * Number(marks[sym])
    const claimedNav = Number(pod.nav)
    return {
      pod_id: id, funded: funded[id] ?? 0, realized: realized[id] ?? 0, cash: cash[id] ?? 0, nav, claimedNav,
      ok: Math.abs(nav - claimedNav) < 0.005 && Math.abs((realized[id] ?? 0) - Number(pod.realized_pnl)) < 0.005,
    }
  })
}

export interface CapitalCheck { review_id: string; seq: number; outcome: string; ok: boolean; problems: string[]; moved: number }

const cents = (v: unknown): number => Math.round(Number(v) * 100)

// Re-checks every Apex capital review against the ledger events alone (mirrors the_reef/allocation/capital.py::verify_capital):
// transfers add up to the reserve change, the reserve it started from is what the funding history says, each transfer exists
// as a SLEEVE_FUNDED event carrying the review id after the decision (and none exist without a decision), reclaims stay within
// the uncommitted cash the evidence recorded, and the fund NAV it quoted is the verified mark of that session.
export function verifyCapital(events: LedgerEventJson[]): { checks: CapitalCheck[]; stray: string[]; ok: boolean } {
  let initial = 0, fundedSoFar = 0
  const navByDay = new Map<string, number>()
  const decisions: { seq: number; p: Record<string, any>; reserve: number }[] = []
  const fundings = new Map<string, { seq: number; sleeve: string; amount: number }[]>()
  for (const e of events) {
    const p = e.payload as Record<string, any>
    if (e.kind === 'EPOCH_OPENED') initial = cents(p.initial_cash)
    else if (e.kind === 'SESSION_MARKED') navByDay.set(String(p.session_day), cents(p.nav))
    else if (e.kind === 'APEX_CAPITAL_DECISION') decisions.push({ seq: e.seq, p, reserve: initial - fundedSoFar })
    else if (e.kind === 'SLEEVE_FUNDED') {
      fundedSoFar += cents(p.amount)
      const k = String(p.ref)
      fundings.set(k, [...(fundings.get(k) ?? []), { seq: e.seq, sleeve: String(p.sleeve_id), amount: cents(p.amount) }])
    }
  }
  const checks: CapitalCheck[] = decisions.map(({ seq, p, reserve }) => {
    const problems: string[] = []
    const moves = (p.transfers as any[]).map(t => ({ sleeve: String(t.sleeve_id), amount: cents(t.amount) }))
    const draw = moves.reduce((a, m) => a + m.amount, 0)
    if (cents(p.reserve_before) !== reserve) problems.push(`reserve before ${p.reserve_before} is not ${(reserve / 100).toFixed(2)} from the funding history`)
    if (cents(p.reserve_after) !== cents(p.reserve_before) - draw) problems.push('transfers do not add up to the change in the reserve')
    const got = (fundings.get(String(p.review_id)) ?? [])
    const key = (x: { sleeve: string; amount: number }) => `${x.sleeve}:${x.amount}`
    if ([...got.map(g => key({ sleeve: g.sleeve, amount: g.amount }))].sort().join('|') !== moves.map(key).sort().join('|')) problems.push('the SLEEVE_FUNDED events do not match the decision\'s transfers')
    if (got.some(g => g.seq < seq)) problems.push('a transfer precedes its decision')
    if (p.outcome === 'HELD' && moves.length) problems.push('a HELD review moved capital')
    if (moves.filter(m => m.amount > 0).length > 1) problems.push('more than one grant')
    for (const m of moves) if (m.amount < 0 && -m.amount > cents(p.evidence[m.sleeve].free_cash)) problems.push(`reclaimed more from ${m.sleeve} than its uncommitted cash`)
    if (navByDay.get(String(p.session_day)) !== cents(p.fund_nav)) problems.push('the quoted fund NAV is not the verified mark of that session')
    return { review_id: String(p.review_id), seq, outcome: String(p.outcome), ok: problems.length === 0, problems, moved: moves.filter(m => m.amount > 0).reduce((a, m) => a + m.amount, 0) / 100 }
  })
  const decided = new Set(decisions.map(d => String(d.p.review_id)))
  const stray = [...fundings.keys()].filter(k => k !== 'd0-initial' && !decided.has(k))
  return { checks, stray, ok: checks.every(c => c.ok) && stray.length === 0 }
}
