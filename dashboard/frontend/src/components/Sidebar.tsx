import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Fish, Briefcase, ArrowLeftRight,
  MapPin, Globe, Lightbulb, FileText, Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import SentimentGauge from './SentimentGauge'

const NAV_ITEMS: { label: string; path: string; icon: LucideIcon }[] = [
  { label: 'Command Center', path: '/',          icon: LayoutDashboard },
  { label: 'Sharks',         path: '/sharks',    icon: Fish },
  { label: 'Portfolio',      path: '/portfolio', icon: Briefcase },
  { label: 'Trades',         path: '/trades',    icon: ArrowLeftRight },
  { label: 'Positions',      path: '/positions', icon: MapPin },
  { label: 'Market Map',     path: '/market',    icon: Globe },
  { label: 'Insights',       path: '/insights',  icon: Lightbulb },
  { label: 'Reports',        path: '/reports',   icon: FileText },
  { label: 'Settings',       path: '/settings',  icon: Settings },
]

const active   = 'flex items-center gap-2.5 px-3 py-2.5 text-sm font-medium border-l-2 border-reef-gain text-reef-gain bg-reef-elevated'
const inactive = 'flex items-center gap-2.5 px-3 py-2.5 text-sm font-medium border-l-2 border-transparent text-slate-400 hover:text-white hover:bg-reef-elevated transition-colors'

export default function Sidebar() {
  return (
    <div
      className="flex flex-col bg-reef-card border-r border-reef-border overflow-hidden"
      style={{ gridColumn: '1', gridRow: '1 / 3' }}
    >
      {/* Logo */}
      <div className="flex flex-col gap-1 px-4 py-5 border-b border-reef-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden>🦈</span>
          <span className="font-sans font-bold text-white text-lg">THE REEF</span>
        </div>
        <div className="text-[9px] font-mono tracking-widest text-slate-500 uppercase">
          AI Trading Command Center
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col py-2 flex-1 overflow-y-auto">
        {NAV_ITEMS.map(({ label, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => isActive ? active : inactive}
          >
            <Icon size={15} className="shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Sentiment gauge pinned to bottom */}
      <div className="px-4 py-4 border-t border-reef-border shrink-0">
        <SentimentGauge score={72} label="Bullish" />
      </div>
    </div>
  )
}
