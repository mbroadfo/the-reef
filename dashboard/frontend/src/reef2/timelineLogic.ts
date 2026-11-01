// Pure rules behind the timeline controls, kept free of React so they can be tested directly.
export interface MarkerLike { index: number; funded: boolean }

// One update for both the session and the selected pitch, so a marker click can never leave them out of step.
export function nextParams(prev: URLSearchParams, index: number, total: number, pitchId?: string | null): URLSearchParams {
  const q = new URLSearchParams(prev)
  const n = Math.max(0, Math.min(total - 1, index))
  q.set('s', String(n + 1))
  if (pitchId) q.set('p', pitchId)
  else q.delete('p')
  return q
}

// Chronological mode shows only decisions that have already happened; retrospective mode shows them all.
export function visibleMarkers<T extends MarkerLike>(markers: T[], viewIndex: number, retrospective: boolean): T[] {
  return retrospective ? markers : markers.filter(m => m.index <= viewIndex)
}

export function sessionParam(raw: string | null, total: number): number {
  const n = Number(raw)
  return n >= 1 && n <= total ? n - 1 : total - 1
}
