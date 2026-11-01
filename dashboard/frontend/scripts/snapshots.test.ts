import { newestSnapshotMs } from '../src/utils/snapshots.ts'
const t = (s: string) => new Date(s).getTime()
const cases: [string, unknown, number | null][] = [
  ['unsorted', newestSnapshotMs([{timestamp:'2026-10-03T20:00:00Z'},{timestamp:'2026-10-29T20:00:00Z'},{timestamp:'2026-10-10T20:00:00Z'}]), t('2026-10-29T20:00:00Z')],
  ['invalid ignored', newestSnapshotMs([{timestamp:'garbage'},{timestamp:'2026-10-10T20:00:00Z'},{timestamp:''}]), t('2026-10-10T20:00:00Z')],
  ['all invalid', newestSnapshotMs([{timestamp:'x'}]), null],
  ['empty', newestSnapshotMs([]), null],
  ['undefined', newestSnapshotMs(undefined), null],
]
let bad = 0
for (const [n, got, want] of cases) { if (got !== want) { bad++; console.log('FAIL', n, got, want) } else console.log('ok  ', n) }
process.exit(bad ? 1 : 0)
