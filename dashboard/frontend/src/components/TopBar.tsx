import { useState, useEffect } from 'react'

function formatTime(d: Date): string {
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: true, timeZone: 'America/New_York',
  }) + ' ET'
}

function formatDate(d: Date): string {
  return d.toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
    timeZone: 'America/New_York',
  })
}

export default function TopBar() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className="flex items-center justify-end px-6 bg-reef-bg border-b border-reef-border"
      style={{ gridColumn: '2 / 4', gridRow: '1', height: '64px' }}
    >
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-reef-elevated border border-reef-border">
        <div className="w-2 h-2 rounded-full bg-reef-gain animate-pulse" />
        <span className="text-sm font-sans text-white">Market Open</span>
        <span className="font-mono text-sm text-slate-400">{formatTime(now)}</span>
        <span className="font-sans text-xs text-slate-500">{formatDate(now)}</span>
      </div>
    </div>
  )
}
