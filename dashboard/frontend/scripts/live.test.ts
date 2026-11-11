// Verifies a LIVE-DATA PAPER snapshot with the same code the Research Lab runs in the browser.
// The live snapshot holds vendor-derived prices and is never committed, so this test runs only when
// REEF_LIVE_SNAPSHOT points at one (tests/live/test_ui_contract.py builds a synthetic-vendor snapshot and does exactly that).
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { recomputePods, verifyCapital, verifyIntegrity } from '../src/reef2/verify.ts'
import { sessionsOf, viewAt } from '../src/reef2/replay.ts'
import type { Snapshot } from '../src/reef2/types.ts'

const path = process.env.REEF_LIVE_SNAPSHOT
if (!path) {
  console.log('live.test.ts: REEF_LIVE_SNAPSHOT not set; skipped (the live snapshot is private and never committed)')
  process.exit(0)
}
const snap = JSON.parse(readFileSync(path, 'utf8')) as Snapshot

assert.equal(snap.mode.kind, 'LIVE_DATA_PAPER')
assert.ok(snap.live, 'the live block is present')
assert.equal(snap.live!.paper_only, true)
assert.equal(snap.live!.execution.basis, 'SIMULATED_FROM_DAILY_OHLC')
assert.ok(['CURRENT', 'AWAITING_VENDOR', 'STALE'].includes(snap.live!.data.freshness))

const header = { events: snap.generated_from.events, head_hash: snap.generated_from.head_hash }
const integrity = await verifyIntegrity(structuredClone(snap.events), header)
assert.ok(integrity.ok, JSON.stringify(integrity.checks.filter(c => !c.ok)))
assert.ok(snap.events.some(e => e.kind === 'ATTESTATION' && (e.payload as any).subtype === 'CHARTER'), 'the charter is in the ledger')
assert.ok(snap.events.some(e => e.kind === 'ATTESTATION' && (e.payload as any).subtype === 'SESSION_DATA'), 'sessions are attested')

// The browser's independent recomputation agrees with the engine's figures, with attestations in the stream.
for (const p of recomputePods(snap)) assert.ok(p.ok, `${p.pod_id}: recomputed NAV ${p.nav} vs claimed ${p.claimedNav}`)
assert.ok(verifyCapital(snap.events).ok)

const sessions = sessionsOf(snap.events)
assert.equal(sessions.length, snap.live!.sessions.processed)
if (sessions.length) {
  const v = viewAt(snap, sessions.length - 1)
  assert.equal(v.pods.length, 2)
}
console.log(`live.test.ts: ${snap.events.length} events, ${sessions.length} sessions verified`)
