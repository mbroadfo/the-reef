// The timeline's contract: a view of session t is built from the ledger up to session t's close and nothing later,
// and the view of the last session equals the engine's own end-of-run figures.
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { sessionsOf, spotlightFor, viewAt } from '../src/reef2/replay.ts'
import { capitalMarkers, decisionMarkers } from '../src/reef2/replay.ts'
import { nextParams, sessionParam, visibleMarkers } from '../src/reef2/timelineLogic.ts'
import type { Snapshot } from '../src/reef2/types.ts'

const snap = JSON.parse(readFileSync(new URL('../public/reef2/snapshot.json', import.meta.url), 'utf8')) as Snapshot
const sessions = sessionsOf(snap.events)
const close = (a: number, b: number, tol = 1e-9) => Math.abs(a - b) <= tol

assert.equal(sessions.length, 70, 'the synthetic competition has 70 sessions')
assert.ok(sessions.every((s, i) => i === 0 || (s.day > sessions[i - 1].day && s.closedSeq > sessions[i - 1].closedSeq)))
assert.equal(sessions[69].day, snap.generated_from.last_session)

// --- the last session reproduces the engine's snapshot -----------------------------------------------------------
{
  const v = viewAt(snap, 69)
  assert.equal(v.eventsVisible, snap.events.length)
  assert.equal(v.headHash, snap.generated_from.head_hash)
  assert.ok(close(v.fundNav, Number(snap.fund.nav), 0.005))
  assert.ok(close(v.fundReturn, snap.fund.return))
  assert.equal(v.pods.length, 2)
  for (const p of v.pods) {
    const s = snap.pods.find(x => x.pod_id === p.pod_id)!
    assert.ok(close(p.nav, Number(s.nav), 0.005), `${p.pod_id} nav`)
    assert.ok(close(p.cash, Number(s.cash), 0.005), `${p.pod_id} cash`)
    assert.ok(close(p.realized, Number(s.realized_pnl), 0.005), `${p.pod_id} realized`)
    assert.ok(close(p.unrealized, Number(s.unrealized_pnl), 0.005), `${p.pod_id} unrealized`)
    assert.ok(close(p.return, s.return!, 1e-9), `${p.pod_id} return`)
    assert.ok(close(p.max_drawdown, s.max_drawdown!, 1e-9), `${p.pod_id} drawdown`)
    assert.ok(close(p.sharpe_like!, s.sharpe_like!, 1e-9), `${p.pod_id} return/risk`)
    assert.ok(close(p.volatility_ann!, s.volatility_ann!, 1e-9), `${p.pod_id} volatility`)
    assert.ok(close(p.avg_exposure, s.avg_exposure!, 1e-9), `${p.pod_id} exposure`)
    assert.equal(p.trades, s.trades)
    assert.ok(close(p.avg_win ?? 0, Number(s.avg_win ?? 0), 0.005) && close(p.avg_loss ?? 0, Number(s.avg_loss ?? 0), 0.005), `${p.pod_id} avg win/loss`)
    assert.ok(close(p.win_rate!, s.win_rate!, 1e-12))
    assert.equal(p.proposals, s.proposals)
    assert.equal(p.funded_proposals, s.funded_proposals)
    assert.equal(p.rank, s.rank, `${p.pod_id} rank`)
    assert.deepEqual(p.positions.map(x => [x.symbol, x.shares]), s.positions!.map(x => [x.symbol, x.shares]))
    for (const x of p.positions) {
      const y = s.positions!.find(q => q.symbol === x.symbol)!
      assert.ok(close(x.mark, Number(y.mark)) && close(x.unrealized, Number(y.unrealized), 0.005) && close(x.stop ?? 0, Number(y.stop ?? 0)), `${p.pod_id} ${x.symbol} position`)
    }
  }
  assert.equal(v.pitches.length, snap.proposals.length)
  for (const r of snap.proposals) {
    const p = v.pitches.find(x => x.proposal_id === r.proposal_id)!
    assert.deepEqual(p.decision, r.decision)
    const want = r.decision!.outcome === 'DECLINED' ? 'DECLINED' : r.lifecycle!.status === 'NOT_FILLED' ? 'NOT_FILLED' : r.lifecycle!.status
    assert.equal(p.state, want, r.proposal_id)
    if (r.lifecycle?.entry) {
      assert.ok(close(p.pnl!, Number(r.lifecycle.pnl), 0.005), `${r.proposal_id} pnl`)
      assert.equal(p.entry!.seq, r.lifecycle.entry.seq)
      assert.equal(p.exit?.seq, r.lifecycle.exit?.seq)
    }
  }
}

// --- no look-ahead, structurally: every fact in every view is dated at or before that view's session ----------------
const DATE = /\d{4}-\d{2}-\d{2}/g
// Dates inside these keys are announced plans or notices (the next valid open, a corporate action's effective date),
// not outcomes; everything else must not be later than the viewed session.
const PLANNED_KEYS = new Set(['fill_session', 'detail'])
function walk(x: unknown, key: string, visit: (k: string, v: unknown) => void) {
  visit(key, x)
  if (Array.isArray(x)) x.forEach(v => walk(v, key, visit))
  else if (x && typeof x === 'object') for (const [k, v] of Object.entries(x)) walk(v, k, visit)
}
for (let t = 0; t < sessions.length; t++) {
  const v = viewAt(snap, t)
  const day = sessions[t].day
  assert.equal(v.day, day)
  assert.equal(v.cutSeq, sessions[t].closedSeq)
  assert.equal(v.eventsVisible, sessions[t].closedSeq, 'exactly the events up to the close are visible')
  walk(v, '', (k, x) => {
    if (typeof x === 'string' && !PLANNED_KEYS.has(k) && k !== 'headHash') {
      for (const d of x.match(DATE) ?? []) assert.ok(d <= day, `session ${day}: "${k}" mentions later date ${d}`)
    }
    if ((k === 'seq' || k === 'packet_seq') && typeof x === 'number') assert.ok(x <= v.cutSeq, `session ${day}: ${k} ${x} is after the cut ${v.cutSeq}`)
  })
  assert.equal(v.fundSeries.length, t + 1)
  assert.ok(v.benchSeries.every(([d]) => d <= day))
  for (const p of v.pods) assert.equal(p.nav_series.length, t + 1)
  for (const s of Object.values(v.prices)) assert.ok(s.every(([d]) => d <= day))
  for (const p of v.pitches) {
    assert.ok(p.as_of_session <= day)
    assert.ok(p.decision === null || p.decision.seq <= v.cutSeq)
    if (p.state === 'QUEUED') assert.ok(!p.entry && !p.exit)
    if (p.state === 'OPEN') assert.ok(p.entry && !p.exit)
    if (p.state === 'DECLINED') assert.ok(!p.entry)
  }
  const sp = spotlightFor(v)
  if (sp) assert.ok(sp.pitch.packet_seq <= v.cutSeq)
}

// --- "the world ends at session t" gives the identical view -----------------------------------------------------------
// Delete everything after t from the snapshot (events, later pitches, outcomes, prices, benchmark) and the view must not change.
function truncated(t: number): Snapshot {
  const cut = sessions[t].closedSeq
  const day = sessions[t].day
  const s = structuredClone(snap)
  s.events = s.events.filter(e => e.seq <= cut)
  s.proposals = s.proposals.filter(r => r.packet_seq <= cut).map(r => {
    const { lifecycle, counterfactual, order, ...rest } = r
    return { ...rest, decision: r.decision && r.decision.seq <= cut ? r.decision : null } as typeof r
  })
  for (const k of Object.keys(s.prices)) s.prices[k] = s.prices[k].filter(([d]) => d <= day)
  s.fund.benchmark.series = s.fund.benchmark.series.filter(([d]) => d <= day)
  s.fund.nav_series = s.fund.nav_series.filter(([d]) => d <= day)
  for (const p of s.pods) { delete p.nav_series; delete p.positions }
  return s
}
for (const t of [0, 1, 2, 9, 19, 33, 34, 49, 61, 68, 69]) {
  const a = viewAt(snap, t)
  const b = viewAt(truncated(t), t)
  b.total = a.total   // the length of the scrubber is the demonstration's calendar, not a result
  assert.deepEqual(a, b, `session ${sessions[t].day}: the view depends on information from after that session`)
}

// --- history is append-only as the timeline advances -------------------------------------------------------------------
{
  let prev = viewAt(snap, 0)
  for (let t = 1; t < sessions.length; t++) {
    const cur = viewAt(snap, t)
    assert.ok(cur.pitches.length >= prev.pitches.length)
    for (const p of prev.pitches) {
      const q = cur.pitches.find(x => x.proposal_id === p.proposal_id)!
      assert.deepEqual(q.packet, p.packet, 'a pitch never changes after it is made')
      assert.deepEqual(q.decision, p.decision, 'a decision never changes after it is made')
      if (p.state === 'CLOSED') assert.deepEqual(q.exit, p.exit), assert.equal(q.pnl, p.pnl)
    }
    for (const pod of cur.pods) {
      const old = prev.pods.find(x => x.pod_id === pod.pod_id)!
      assert.ok(pod.trades >= old.trades && pod.proposals >= old.proposals)
      assert.deepEqual(pod.nav_series.slice(0, -1), old.nav_series, 'earlier NAVs are never restated')
    }
    prev = cur
  }
}

// --- one known story, session by session ---------------------------------------------------------------------------------
{
  const id = 'momentum:2026-08-19:DIPC'
  const row = snap.proposals.find(r => r.proposal_id === id)!
  const at = (day: string) => viewAt(snap, sessions.findIndex(s => s.day === day)).pitches.find(p => p.proposal_id === id)
  assert.equal(at('2026-08-19')!.state, 'QUEUED')
  assert.equal(at('2026-08-19')!.entry, undefined)
  const filled = at(row.lifecycle!.entry!.session_day)!
  assert.equal(filled.state, 'OPEN')
  assert.equal(filled.entry!.price, 123.56)
  assert.equal(filled.entry!.shares, 8)
  const exitDay = row.lifecycle!.exit!.session_day
  const dayBefore = sessions[sessions.findIndex(s => s.day === exitDay) - 1].day
  assert.equal(at(dayBefore)!.state, 'OPEN')
  const closed = at(exitDay)!
  assert.equal(closed.state, 'CLOSED')
  assert.ok(close(closed.pnl!, 194.64, 0.005))
  assert.match(closed.exit!.reason, /Stopped out/)
}

// --- timeline controls -------------------------------------------------------------------------------------------------
{
  // Chronological mode never shows a decision from a later session; retrospective mode shows all of them.
  const markers = decisionMarkers(snap)
  assert.ok(markers.length > 10)
  for (const t of [0, 5, 23, 45, 69]) {
    const shown = visibleMarkers(markers, t, false)
    assert.ok(shown.every(m => m.index <= t), `session ${t + 1}: a future marker is visible`)
    assert.equal(shown.length, markers.filter(m => m.index <= t).length)
    assert.equal(visibleMarkers(markers, t, true).length, markers.length)
  }
  assert.ok(visibleMarkers(markers, 0, false).length < markers.length)

  // A marker click sets the session and the pitch in one update; neither can be lost or left stale.
  const m = markers.find(x => x.funded && x.index > 10)!
  const before = new URLSearchParams('s=3&p=old')
  const after = nextParams(before, m.index, 70, m.proposal_id)
  assert.equal(after.get('s'), String(m.index + 1))
  assert.equal(after.get('p'), m.proposal_id)
  assert.equal(nextParams(after, 40, 70).get('p'), null, 'moving the timeline clears the selected pitch')
  assert.equal(nextParams(new URLSearchParams(''), 999, 70).get('s'), '70')
  assert.equal(nextParams(new URLSearchParams(''), -4, 70).get('s'), '1')
  assert.equal(sessionParam(null, 70), 69)
  assert.equal(sessionParam('0', 70), 69)
  assert.equal(sessionParam('24', 70), 23)
  // The pitch a marker selects exists at the marker's own session and was decided there.
  for (const mk of markers) {
    const v = viewAt(snap, mk.index)
    const p = v.pitches.find(x => x.proposal_id === mk.proposal_id)
    assert.ok(p && p.decided_today, `marker ${mk.proposal_id} must be visible and decided at its own session`)
  }
}

// --- capital: reviews appear when they happen, transfers are never returns, and every session reconciles ------------
{
  const cm = capitalMarkers(snap)
  assert.ok(cm.length >= 4 && cm.some(m => m.moved) && cm.some(m => !m.moved), 'both moved and held reviews exist')
  assert.deepEqual(cm.map(m => m.index), [...cm.map(m => m.index)].sort((a, b) => a - b))
  const first = cm[0].index
  assert.equal(viewAt(snap, first - 1).reviews.length, 0, 'no review is visible before it is decided')
  const at = viewAt(snap, first)
  assert.equal(at.reviews.length, 1)
  assert.equal(at.reviewsToday.length, 1)
  assert.equal(viewAt(snap, first + 1).reviewsToday.length, 0)
  assert.deepEqual(visibleMarkers(cm, first - 1, false), [], 'chronological mode hides future reviews')
  assert.equal(visibleMarkers(cm, first - 1, true).length, cm.length)

  let prevReturn: Record<string, number> = {}
  for (let i = 0; i < sessions.length; i++) {
    const v = viewAt(snap, i)
    const controlled = v.pods.reduce((a, p) => a + p.controlled, 0)
    assert.ok(close(controlled + v.reserve, v.fundNav, 0.005), `session ${i + 1}: sleeves plus reserve equal the fund NAV`)
    for (const p of v.pods) {
      // capital controlled = capital contributed + investment P&L, so transfers can only ever show up as contributed capital
      assert.ok(close(p.controlled, p.funded + p.realized + p.unrealized, 0.01), `${p.pod_id} session ${i + 1}: controlled = funded + P&L`)
      assert.ok(close(p.pnl, p.realized + p.unrealized, 1e-9))
      assert.ok(close(p.funded, p.initial_funded + p.net_transfers, 1e-9))
      assert.ok(p.cash >= -1e-9, 'no negative cash')
      // the session in which a transfer lands (the next one) must not show a return jump of the transfer's size
      if (v.reviewsToday.some(r => r.transfers.some(t => t.sleeve_id === p.pod_id && t.amount > 0))) {
        const next = viewAt(snap, Math.min(i + 1, sessions.length - 1))
        const q = next.pods.find(x => x.pod_id === p.pod_id)!
        const grant = v.reviewsToday[0].transfers.find(t => t.sleeve_id === p.pod_id)!.amount
        assert.ok(Math.abs(q.return - p.return) < grant / p.nav / 2, `${p.pod_id}: a $${grant} grant is not a return`)
      }
      prevReturn[p.pod_id] = p.return
    }
  }
  // The capital chart and the summary bar are the same numbers: at every session the chart's last point is the post-review balance.
  for (let i = 0; i < sessions.length; i++) {
    const v = viewAt(snap, i)
    const last = v.capital[v.capital.length - 1]
    assert.equal(last.day, v.day)
    for (const p of v.pods) assert.ok(close(last.pods[p.pod_id], p.controlled, 0.005), `session ${i + 1} ${p.pod_id}: chart ${last.pods[p.pod_id]} vs bar ${p.controlled}`)
    assert.ok(close(last.reserve, v.reserve, 0.005), `session ${i + 1}: chart reserve ${last.reserve} vs bar ${v.reserve}`)
  }
  {
    const at = (n: number) => viewAt(snap, n - 1).capital.at(-1)!
    assert.ok(close(at(15).pods.momentum, 3685.16, 0.005) && close(at(15).pods.contrarian, 2470.17, 0.005), 'session 15 shows the balances after the $500 transfer')
    // Review 35 holds (the leader's proposal evidence no longer counts the untradable DEAL), so only 15 and 25 move capital.
    assert.equal(viewAt(snap, 34).reviewsToday[0].outcome, 'HELD')
    for (const n of [15, 25]) {
      const r = viewAt(snap, n - 1).reviewsToday[0]
      const to = r.transfers.find(t => t.amount > 0)!
      const before = viewAt(snap, n - 2).capital.at(-1)!.pods[to.sleeve_id]
      assert.ok(at(n).pods[to.sleeve_id] > before - 200, `session ${n}: the grant is in the chart`)
    }
    // no look-ahead: an earlier view never contains a later session's point
    assert.ok(viewAt(snap, 10).capital.every(c => c.day <= viewAt(snap, 10).day) && viewAt(snap, 10).capital.length === 11)
  }
  // Transfers recorded in a review are the ones the ledger shows, with their event numbers.
  for (const r of viewAt(snap, 69).reviews) {
    assert.ok(r.transfers.every(t => t.seq !== null && t.seq > r.seq), 'each transfer points at its SLEEVE_FUNDED event after the decision')
    assert.ok(close(r.transfers.reduce((a, t) => a + t.amount, 0), r.reserve_before - r.reserve_after, 0.005))
    assert.ok(r.rationale.length > 20 && r.reasons.length > 0)
  }
}

console.log('reef2 replay tests passed')
