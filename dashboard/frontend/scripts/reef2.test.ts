// Verifies the committed aquarium snapshot with the same code the Research Lab runs in the browser.
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { canonical, recomputePods, verifyChain } from '../src/reef2/verify.ts'
import type { Snapshot } from '../src/reef2/types.ts'

const snap = JSON.parse(readFileSync(new URL('../public/reef2/snapshot.json', import.meta.url), 'utf8')) as Snapshot

assert.equal(canonical({ b: 1, a: ['x', null, { z: 'é', y: 2 }] }), '{"a":["x",null,{"y":2,"z":"\\u00e9"}],"b":1}')

const chain = await verifyChain(snap.events)
assert.ok(chain.ok, `hash chain broken at seq ${chain.firstBadSeq}`)
assert.equal(chain.checked, snap.events.length)
assert.equal(chain.head, snap.generated_from.head_hash)

// Tampering with any figure breaks the chain at that event.
const tampered = structuredClone(snap.events)
const fill = tampered.find(e => e.kind === 'FILL')!
;(fill.payload as Record<string, unknown>).price = '1.00'
const broken = await verifyChain(tampered)
assert.equal(broken.ok, false)
assert.equal(broken.firstBadSeq, fill.seq)

const pods = recomputePods(snap)
assert.ok(pods.length >= 2, 'at least two active pods')
for (const p of pods) assert.ok(p.ok, `${p.pod_id}: recomputed NAV ${p.nav} != claimed ${p.claimedNav}`)

assert.equal(snap.pods.length, 6)
assert.ok(snap.pods.filter(p => p.status === 'INACTIVE').every(p => p.inactive_reason.length > 0 && p.nav === undefined),
  'inactive pods carry a reason and no invented numbers')
assert.ok(snap.proposals.every(r => r.decision !== null), 'every proposal has an Apex decision')
assert.ok(snap.checks.every(c => c.ok), 'server-side checks all pass')
console.log('reef2 snapshot tests passed')
