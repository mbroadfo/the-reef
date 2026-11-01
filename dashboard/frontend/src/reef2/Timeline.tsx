import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { POD_HEX } from './PodShark'
import { dayLabel } from './format'
import { decisionMarkers, sessionsOf, viewAt } from './replay'
import type { Marker, SessionView } from './replay'
import type { Snapshot } from './types'

export interface Timeline {
  view: SessionView
  markers: Marker[]
  days: string[]
  playing: boolean
  speed: number
  pauseAtFunded: boolean
  selected: string | null
  go: (i: number) => void
  select: (proposalId: string | null) => void
  toggle: () => void
  stop: () => void
  setSpeed: (n: number) => void
  setPauseAtFunded: (b: boolean) => void
  prevPitch: () => void
  nextPitch: () => void
}

// The timeline position lives in the URL (?s=session number, ?p=selected pitch) so a moment can be linked and revisited.
export function useTimeline(snap: Snapshot): Timeline {
  const [params, setParams] = useSearchParams()
  const days = useMemo(() => sessionsOf(snap.events).map(s => s.day), [snap])
  const total = days.length
  const markers = useMemo(() => decisionMarkers(snap), [snap])
  const raw = Number(params.get('s'))
  const index = raw >= 1 && raw <= total ? raw - 1 : total - 1
  const view = useMemo(() => viewAt(snap, index), [snap, index])
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [pauseAtFunded, setPauseAtFunded] = useState(false)

  const go = useCallback((i: number) => {
    const n = Math.max(0, Math.min(total - 1, i))
    setParams(prev => { const q = new URLSearchParams(prev); q.set('s', String(n + 1)); q.delete('p'); return q }, { replace: true })
  }, [setParams, total])
  const select = useCallback((id: string | null) => {
    setParams(prev => { const q = new URLSearchParams(prev); if (id) q.set('p', id); else q.delete('p'); return q }, { replace: true })
  }, [setParams])

  useEffect(() => {
    if (!playing) return
    if (index >= total - 1) { setPlaying(false); return }
    const t = setTimeout(() => go(index + 1), 1100 / speed)
    return () => clearTimeout(t)
  }, [playing, index, speed, total, go])

  useEffect(() => {
    if (playing && pauseAtFunded && view.today.some(p => p.decision?.outcome === 'FUNDED')) setPlaying(false)
  }, [view.index]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () => {
    if (playing) { setPlaying(false); return }
    if (index >= total - 1) go(0)
    setPlaying(true)
  }
  const fundedIdx = Array.from(new Set(markers.filter(m => m.funded).map(m => m.index))).sort((a, b) => a - b)
  const prevPitch = () => { setPlaying(false); const t = [...fundedIdx].reverse().find(i => i < index); if (t !== undefined) go(t) }
  const nextPitch = () => { setPlaying(false); const t = fundedIdx.find(i => i > index); if (t !== undefined) go(t) }
  return {
    view, markers, days, playing, speed, pauseAtFunded, selected: params.get('p'),
    go, select, toggle, stop: () => setPlaying(false), setSpeed, setPauseAtFunded, prevPitch, nextPitch,
  }
}

export function TimelineBar({ tl }: { tl: Timeline }) {
  const { view, markers } = tl
  const last = view.total - 1
  const frac = (i: number) => (last ? i / last : 0)
  const hasPrev = markers.some(m => m.funded && m.index < view.index)
  const hasNext = markers.some(m => m.funded && m.index > view.index)
  const here = markers.filter(m => m.index === view.index)
  return (
    <div className="timeline-bar sticky bottom-3 z-30 mt-6 px-3 pb-2 pt-2 sm:px-4" role="group" aria-label="Competition timeline">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="mr-auto min-w-0">
          <span className="font-mono text-sm font-bold text-white">Session {view.index + 1}<span className="text-slate-500"> / {view.total}</span></span>
          <span className="ml-2 text-sm text-slate-300">{dayLabel(view.day)}</span>
          <span className="chip chip-warn ml-2 align-middle">SYNTHETIC REPLAY</span>
        </div>
        <label className="hidden items-center gap-1.5 text-xs text-slate-400 sm:flex">
          <input type="checkbox" checked={tl.pauseAtFunded} onChange={e => tl.setPauseAtFunded(e.target.checked)} /> pause at funded pitches
        </label>
        <label className="flex items-center gap-1 text-xs text-slate-400">speed
          <select aria-label="Playback speed" className="rounded-md border border-slate-700 bg-slate-900 px-1 py-0.5 text-slate-200" value={tl.speed} onChange={e => tl.setSpeed(Number(e.target.value))}>
            <option value={0.5}>0.5x</option><option value={1}>1x</option><option value={2}>2x</option><option value={4}>4x</option>
          </select>
        </label>
      </div>

      <div className="relative mt-1 h-4">
        {markers.map(m => (
          <button key={m.proposal_id} type="button" onClick={() => { tl.stop(); tl.go(m.index); tl.select(m.proposal_id) }}
                  aria-label={`Session ${m.index + 1}: ${m.pod_id} ${m.funded ? 'funded' : 'declined'} ${m.symbol}`}
                  title={`${dayLabel(tl.days[m.index])}: ${m.pod_id} ${m.funded ? 'funded' : 'declined'} ${m.symbol}`}
                  className="absolute top-0.5 h-3 w-3 -translate-x-1/2 rounded-full"
                  style={{ left: `calc(${frac(m.index)} * (100% - 18px) + 9px)`, background: m.funded ? POD_HEX[m.pod_id] : 'transparent', border: `1.5px solid ${m.funded ? POD_HEX[m.pod_id] : '#64748b'}`, opacity: m.index === view.index ? 1 : 0.8 }} />
        ))}
      </div>
      <input type="range" className="scrub" min={1} max={view.total} value={view.index + 1} aria-label="Session"
             onChange={e => { tl.stop(); tl.go(Number(e.target.value) - 1) }} />

      <div className="mt-1 flex flex-wrap items-center gap-2">
        <button className="tl-btn px-3 text-xs" onClick={tl.prevPitch} disabled={!hasPrev} aria-label="Previous funded pitch">◂ pitch</button>
        <button className="tl-btn" onClick={() => { tl.stop(); tl.go(view.index - 1) }} disabled={view.index === 0} aria-label="Previous session">‹</button>
        <button className="tl-btn tl-play px-4" onClick={tl.toggle} aria-label={tl.playing ? 'Pause' : view.index >= last ? 'Replay from the start' : 'Play'}>
          {tl.playing ? '❚❚ Pause' : view.index >= last ? '↺ Replay' : '▶ Play'}
        </button>
        <button className="tl-btn" onClick={() => { tl.stop(); tl.go(view.index + 1) }} disabled={view.index >= last} aria-label="Next session">›</button>
        <button className="tl-btn px-3 text-xs" onClick={tl.nextPitch} disabled={!hasNext} aria-label="Next funded pitch">pitch ▸</button>
        <span className="ml-auto hidden text-xs text-slate-500 md:inline">
          ledger as of #{view.cutSeq} · {here.length ? `${here.length} marked decision${here.length > 1 ? 's' : ''} today` : 'dots: filled = funded, hollow = declined'}
        </span>
      </div>
    </div>
  )
}
