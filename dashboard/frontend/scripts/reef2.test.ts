// Verifies the committed aquarium snapshot with the same code the Research Lab runs in the browser,
// and proves the integrity check catches altered, omitted, reordered and truncated events.
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'
import { canonical, recomputePods, verifyIntegrity } from '../src/reef2/verify.ts'
import type { LedgerEventJson, Snapshot } from '../src/reef2/types.ts'

const snap = JSON.parse(readFileSync(new URL('../public/reef2/snapshot.json', import.meta.url), 'utf8')) as Snapshot
const header = { events: snap.generated_from.events, head_hash: snap.generated_from.head_hash }
const fresh = (): LedgerEventJson[] => structuredClone(snap.events)
const failing = (r: Awaited<ReturnType<typeof verifyIntegrity>>) => r.checks.filter(c => !c.ok).map(c => c.name.split(':')[0].split(' ').slice(0, 2).join(' '))
const sha = (t: string) => createHash('sha256').update(t).digest('hex')

assert.equal(canonical({ b: 1, a: ['x', null, { z: 'é', y: 2 }] }), '{"a":["x",null,{"y":2,"z":"\\u00e9"}],"b":1}')

// --- the committed snapshot is intact --------------------------------------------------------------------
const clean = await verifyIntegrity(fresh(), header)
assert.ok(clean.ok, JSON.stringify(clean.checks.filter(c => !c.ok)))
assert.equal(clean.count, snap.events.length)
assert.equal(clean.checks.length, 5)
assert.ok((await verifyIntegrity(fresh(), header, snap.generated_from.head_hash.toUpperCase().toLowerCase())).ok, 'a matching external checkpoint passes')

// --- altered event -----------------------------------------------------------------------------------------
{
  const ev = fresh()
  const fill = ev.find(e => e.kind === 'FILL')!
  ;(fill.payload as Record<string, unknown>).price = '1.00'
  const r = await verifyIntegrity(ev, header)
  assert.equal(r.ok, false)
  assert.equal(r.firstBadSeq, fill.seq)
  assert.ok(r.checks.find(c => c.name.startsWith('Each event'))!.ok === false, 'content hash check fails')
}

// --- omitted event (middle) -------------------------------------------------------------------------------
{
  const ev = fresh()
  const gone = ev.splice(100, 1)[0]
  const r = await verifyIntegrity(ev, header)
  assert.equal(r.ok, false)
  assert.equal(r.firstBadSeq, gone.seq + 1, 'the first event after the gap is flagged')
  assert.ok(!r.checks.find(c => c.name.startsWith('Sequence'))!.ok, 'sequence check fails')
  assert.ok(!r.checks.find(c => c.name.startsWith('Hash-chain'))!.ok, 'continuity check fails')
  assert.ok(!r.checks.find(c => c.name.startsWith('Event count'))!.ok, 'count check fails')
}

// --- reordered / duplicated events ---------------------------------------------------------------------------
{
  const ev = fresh()
  ;[ev[50], ev[51]] = [ev[51], ev[50]]
  assert.equal((await verifyIntegrity(ev, header)).ok, false)
  const dup = fresh()
  dup.splice(60, 0, structuredClone(dup[60]))
  const r = await verifyIntegrity(dup, header)
  assert.equal(r.ok, false)
  assert.ok(!r.checks.find(c => c.name.startsWith('Sequence'))!.ok)
}

// --- truncated tail ----------------------------------------------------------------------------------------
{
  const ev = fresh().slice(0, -7)
  const r = await verifyIntegrity(ev, header)
  assert.equal(r.ok, false)
  // The truncated chain is still internally consistent: only the header comparison catches it.
  assert.ok(r.checks.find(c => c.name.startsWith('Sequence'))!.ok)
  assert.ok(r.checks.find(c => c.name.startsWith('Hash-chain'))!.ok)
  assert.ok(r.checks.find(c => c.name.startsWith('Each event'))!.ok)
  assert.deepEqual(failing(r).sort(), ['Event count', 'Final head'])
  assert.match(r.checks.find(c => c.name.startsWith('Event count'))!.detail, /truncated/)
}

// --- the stated limit: a fully rewritten snapshot passes the self-check but not an independent checkpoint ----
{
  const ev = fresh()
  const target = ev.find(e => e.kind === 'FILL')!
  ;(target.payload as Record<string, unknown>).price = '1.00'
  let prev = '0'.repeat(64)
  for (const e of ev) {   // an attacker re-hashes everything after the edit, including the header
    e.prev_hash = prev
    const content = { event_id: e.event_id, epoch_id: e.epoch_id, kind: e.kind, occurred_at: e.occurred_at, payload: e.payload }
    e.hash = sha(`${e.seq}|${e.prev_hash}|${sha(canonical(content))}`)
    prev = e.hash
  }
  const forgedHeader = { events: ev.length, head_hash: prev }
  assert.ok((await verifyIntegrity(ev, forgedHeader)).ok, 'self-contained check cannot see a consistent rewrite')
  const external = await verifyIntegrity(ev, forgedHeader, snap.generated_from.head_hash)
  assert.equal(external.ok, false, 'an independently recorded head hash does')
}

// --- books -----------------------------------------------------------------------------------------------
const pods = recomputePods(snap)
assert.ok(pods.length >= 2, 'at least two active pods')
for (const p of pods) assert.ok(p.ok, `${p.pod_id}: recomputed NAV ${p.nav} != claimed ${p.claimedNav}`)

assert.equal(snap.pods.length, 6)
assert.ok(snap.pods.filter(p => p.status === 'INACTIVE').every(p => p.inactive_reason.length > 0 && p.nav === undefined),
  'inactive pods carry a reason and no invented numbers')
assert.ok(snap.proposals.every(r => r.decision !== null), 'every proposal has an Apex decision')
assert.ok(snap.checks.every(c => c.ok), 'server-side checks all pass')
assert.equal(snap.apex.allocation_mode, 'FIXED_SLEEVES')
assert.equal(snap.apex.dynamic_reallocation, false)
console.log('reef2 snapshot tests passed')
