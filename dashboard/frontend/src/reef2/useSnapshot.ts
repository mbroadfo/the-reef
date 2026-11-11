import { useEffect, useState } from 'react'
import type { Snapshot } from './types'

// The page renders only what the engine wrote to this file; there is no other data source.
// Two separate epochs share the page: the synthetic demonstration at "/" and the real-market-data paper epoch at "/live".
// The live snapshot is private (vendor prices): it is produced locally by tools/live.py and never committed.
export const IS_LIVE = typeof window !== 'undefined' && /^\/live(\/|$)/.test(window.location.pathname)
const BASE = ((import.meta.env.VITE_SNAPSHOT_BASE as string | undefined) ?? '').replace(/\/$/, '')
const SNAPSHOT_URL = `${BASE}/reef2/${IS_LIVE ? 'live/' : ''}snapshot.json`

let cache: Promise<Snapshot> | null = null
export const loadSnapshot = (): Promise<Snapshot> =>
  (cache ??= fetch(SNAPSHOT_URL).then(r => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    return r.json() as Promise<Snapshot>
  }))

export function useSnapshot(): { snap: Snapshot | null; error: string | null } {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    loadSnapshot().then(setSnap).catch(e => { cache = null; setError(String(e)) })
  }, [])
  return { snap, error }
}
