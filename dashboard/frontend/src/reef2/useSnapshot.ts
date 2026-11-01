import { useEffect, useState } from 'react'
import type { Snapshot } from './types'

// The page renders only what the engine wrote to this file; there is no other data source.
const SNAPSHOT_URL = `${((import.meta.env.VITE_SNAPSHOT_BASE as string | undefined) ?? '').replace(/\/$/, '')}/reef2/snapshot.json`

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
