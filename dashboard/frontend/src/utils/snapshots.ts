// Epoch milliseconds of the newest snapshot with a parseable timestamp, or null.
// The API does not promise ordering, so never assume the last element is the latest.
export function newestSnapshotMs(snapshots: ReadonlyArray<{ timestamp: string }> | null | undefined): number | null {
  let newest: number | null = null
  for (const s of snapshots ?? []) {
    const ms = new Date(s.timestamp).getTime()
    if (Number.isFinite(ms) && (newest === null || ms > newest)) newest = ms
  }
  return newest
}
