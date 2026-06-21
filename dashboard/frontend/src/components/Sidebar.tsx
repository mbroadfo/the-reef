import { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import SentimentGauge from './SentimentGauge'
import reefLogo from '../assets/the_reef_logo.png'
import { fetchSentiment } from '../api'
import type { Sentiment } from '../types'

const NAV_ITEMS: { label: string; path: string; emoji: string }[] = [
  { label: 'Command Center', path: '/',          emoji: '⚡' },
  { label: 'Sharks',         path: '/sharks',    emoji: '🦈' },
  { label: 'Portfolio',      path: '/portfolio', emoji: '📊' },
  { label: 'Trades',         path: '/trades',    emoji: '↗️' },
  { label: 'Positions',      path: '/positions', emoji: '📍' },
  { label: 'Market Map',     path: '/market',    emoji: '🌐' },
  { label: 'Insights',       path: '/insights',  emoji: '💡' },
  { label: 'Reports',        path: '/reports',   emoji: '📋' },
  { label: 'Settings',       path: '/settings',  emoji: '⚙️' },
]

const active   = 'flex items-center gap-3 px-3 py-2.5 font-medium border-l-2 border-reef-gain text-reef-gain bg-reef-elevated'
const inactive = 'flex items-center gap-3 px-3 py-2.5 font-medium border-l-2 border-transparent text-slate-400 hover:text-white hover:bg-reef-elevated transition-colors'

export default function Sidebar() {
  const [sentiment, setSentiment] = useState<Sentiment | null>(null)

  useEffect(() => {
    const load = () => fetchSentiment().then(setSentiment).catch(() => {})
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="flex flex-col bg-reef-card border-r border-reef-border overflow-hidden h-full">
      {/* Logo */}
      <div className="flex flex-col gap-1 px-4 py-5 border-b border-reef-border shrink-0">
        <div className="flex items-center gap-2">
          <img src={reefLogo} alt="The Reef" style={{ height: '48px', width: 'auto', filter: 'brightness(1.4) drop-shadow(0 0 6px rgba(0,255,136,0.3))' }} />
        </div>
        <div className="text-[9px] font-mono tracking-widest text-slate-500 uppercase">
          AI Trading Command Center
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col py-2 flex-1 overflow-y-auto">
        {NAV_ITEMS.map(({ label, path, emoji }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => isActive ? active : inactive}
            style={{ fontSize: '15px' }}
          >
            <span style={{ fontSize: '16px', lineHeight: 1, width: '20px', textAlign: 'center', flexShrink: 0 }}>{emoji}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Sentiment gauge + quote pinned to bottom */}
      <div className="border-t border-reef-border shrink-0">
        <div className="px-4 pt-4 pb-2">
          <SentimentGauge score={sentiment?.score ?? 0} label={sentiment?.label} />
        </div>
        <div className="px-4 pb-4 text-center">
          <div className="text-[10px] text-slate-600 italic leading-relaxed">
            "The best traders don't predict the future, they prepare for it."
          </div>
          <div className="text-[10px] text-slate-700 mt-1 not-italic">— The Reef</div>
        </div>
      </div>
    </div>
  )
}
