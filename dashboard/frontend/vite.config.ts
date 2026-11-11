import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// The LIVE-DATA PAPER snapshot holds vendor-derived prices and is private. It must be servable by the local dev and
// preview servers and must never reach a production artifact. Vite copies everything under public/ into dist/, so the
// live snapshot lives OUTSIDE public/ (default .live-snapshot/, override with REEF_LIVE_UI_DIR; tools/live.py writes it there)
// and is served only through the middleware below, which build does not run. The build guard fails a build that contains
// a live snapshot anyway (a stray copy under public/, say).
const here = dirname(fileURLToPath(import.meta.url))
export const LIVE_URL = '/reef2/live/snapshot.json'
const liveDir = (): string => resolve(process.env.REEF_LIVE_UI_DIR ?? join(here, '.live-snapshot'))

function serveLive(): Plugin {
  const handler = (req: { url?: string }, res: any, next: () => void) => {
    if (!req.url || req.url.split('?')[0] !== LIVE_URL) return next()
    const file = join(liveDir(), 'snapshot.json')
    if (!existsSync(file)) { res.statusCode = 404; res.end('no live snapshot'); return }
    res.setHeader('Content-Type', 'application/json')
    res.setHeader('Cache-Control', 'no-store')
    res.end(readFileSync(file))
  }
  return {
    name: 'reef-serve-live-snapshot',
    apply: (_config, env) => env.command === 'serve',
    configureServer(server) { server.middlewares.use(handler) },
    configurePreviewServer(server) { server.middlewares.use(handler) },
  }
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap(n => { const p = join(dir, n); return statSync(p).isDirectory() ? walk(p) : [p] })
}

function forbidLiveInBuild(): Plugin {
  let outDir = 'dist'
  return {
    name: 'reef-forbid-live-snapshot-in-build',
    apply: 'build',
    configResolved(c) { outDir = resolve(c.root, c.build.outDir) },
    closeBundle() {
      if (!existsSync(outDir)) return
      const bad = walk(outDir).filter(p => /[\\/]reef2[\\/]live[\\/]/.test(p) || (p.endsWith('.json') && readFileSync(p, 'utf8').includes('"LIVE_DATA_PAPER"')))
      if (bad.length) throw new Error(`live-paper data must never be part of a production build; found: ${bad.join(', ')}`)
    },
  }
}

export default defineConfig({
  plugins: [react(), serveLive(), forbidLiveInBuild()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
