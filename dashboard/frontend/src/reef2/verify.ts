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

export interface ChainResult { ok: boolean; checked: number; firstBadSeq: number | null; head: string }

export async function verifyChain(events: LedgerEventJson[]): Promise<ChainResult> {
  let prev = GENESIS
  for (const e of events) {
    const content = { event_id: e.event_id, epoch_id: e.epoch_id, kind: e.kind, occurred_at: e.occurred_at, payload: e.payload }
    const fingerprint = await sha256(canonical(content))
    const expected = await sha256(`${e.seq}|${prev}|${fingerprint}`)
    if (e.prev_hash !== prev || e.hash !== expected) return { ok: false, checked: e.seq - 1, firstBadSeq: e.seq, head: prev }
    prev = e.hash
  }
  return { ok: true, checked: events.length, firstBadSeq: null, head: prev }
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
