// Regression: a private LIVE-DATA PAPER snapshot (vendor-derived prices) must never be part of a production build.
// Builds the real app into a scratch directory with a representative live snapshot in the live UI folder and checks that
// nothing from it reaches the output; then plants a stray copy under public/ (which Vite would copy) and checks the build refuses.
// REEF_LIVE_SNAPSHOT may point at a snapshot made by the live runner (tests/live/test_ui_contract.py does); otherwise a synthetic one is used.
import { execFileSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const vite = join(root, 'node_modules', 'vite', 'bin', 'vite.js')
const MARKER_PRICE = '98765.4321'
const MARKER_HASH = 'f00dfacecafebeef'.repeat(4)
const synthetic = {
  mode: { kind: 'LIVE_DATA_PAPER' }, generated_from: { epoch_id: 'live-paper-1999-01-04', head_hash: MARKER_HASH, events: 1 },
  events: [{ seq: 1, kind: 'FILL', payload: { symbol: 'ZZZZ', price: MARKER_PRICE } }],
}
const given = process.env.REEF_LIVE_SNAPSHOT
const snapText = given ? readFileSync(given, 'utf8') : JSON.stringify(synthetic)
const snap = JSON.parse(snapText)
const markers = [snap.generated_from.head_hash, snap.generated_from.epoch_id, ...(given ? [] : [MARKER_PRICE])]

const walk = (d: string): string[] => readdirSync(d).flatMap(n => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p] })
const scratch = mkdtempSync(join(tmpdir(), 'reef-build-'))
const uiDir = join(scratch, 'live-ui')
mkdirSync(uiDir)
writeFileSync(join(uiDir, 'snapshot.json'), snapText)
const env = { ...process.env, REEF_LIVE_UI_DIR: uiDir }
const build = (out: string) => execFileSync(process.execPath, [vite, 'build', '--outDir', out, '--emptyOutDir'], { cwd: root, env, stdio: 'pipe' })

try {
  // 1. The live snapshot sits in the live UI folder: the production build must contain none of it.
  const out = join(scratch, 'dist')
  build(out)
  const files = walk(out)
  assert.ok(files.some(f => f.endsWith('index.html')), 'the build produced the app')
  assert.ok(files.some(f => /reef2[\\/]snapshot\.json$/.test(f)), 'the synthetic demonstration is still shipped')
  assert.deepEqual(files.filter(f => /[\\/]live[\\/]/.test(f) || /live-ui/.test(f)), [], 'no live path in dist')
  for (const f of files) {
    const text = readFileSync(f, 'utf8')
    assert.ok(!(f.endsWith('.json') && text.includes('"LIVE_DATA_PAPER"')), `${f} carries live-paper data`)
    for (const m of markers) assert.ok(!text.includes(m), `${f} contains live snapshot content (${m.slice(0, 12)})`)
  }

  // 2. A stray copy under public/ would be copied by Vite: the build must fail rather than ship it.
  const stray = join(root, 'public', 'reef2', 'live')
  assert.ok(!existsSync(stray), 'no stray live folder before the test')
  mkdirSync(stray, { recursive: true })
  try {
    cpSync(join(uiDir, 'snapshot.json'), join(stray, 'snapshot.json'))
    assert.throws(() => build(join(scratch, 'dist-stray')), /Command failed/, 'a build containing a live snapshot must fail')
  } finally {
    rmSync(stray, { recursive: true, force: true })
  }
  console.log(`build-isolation.test.ts: live snapshot absent from production build (${files.length} files checked); stray public copy rejected`)
} finally {
  rmSync(scratch, { recursive: true, force: true })
}
