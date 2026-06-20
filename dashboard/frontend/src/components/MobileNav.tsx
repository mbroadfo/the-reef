import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  X, LayoutDashboard, Fish, Briefcase, ArrowLeftRight,
  MapPin, Globe, Lightbulb, FileText, Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import reefLogo from '../assets/the_reef_logo.png'

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

const active   = 'flex items-center gap-3 px-4 py-3.5 text-sm font-medium border-l-2 border-reef-gain text-reef-gain bg-reef-elevated'
const inactive = 'flex items-center gap-3 px-4 py-3.5 text-sm font-medium border-l-2 border-transparent text-slate-400 hover:text-white hover:bg-reef-elevated transition-colors'

export default function MobileNav({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.65)',
          backdropFilter: 'blur(3px)',
          zIndex: 40,
          transition: 'opacity 0.2s',
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
        }}
      />

      {/* Drawer */}
      <div style={{
        position: 'fixed', top: 0, left: 0, bottom: 0,
        width: '272px',
        background: 'var(--reef-card)',
        borderRight: '1px solid var(--reef-border)',
        zIndex: 50,
        display: 'flex', flexDirection: 'column',
        transform: open ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 16px 16px',
          borderBottom: '1px solid var(--reef-border)',
          flexShrink: 0,
        }}>
          <div>
            <img src={reefLogo} alt="The Reef" style={{ height: '28px', width: 'auto' }} />
            <div style={{ fontSize: '9px', fontFamily: 'monospace', letterSpacing: '0.1em', color: '#64748b', textTransform: 'uppercase', marginTop: '3px' }}>
              AI Trading Command Center
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '6px', borderRadius: '6px' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflowY: 'auto', paddingTop: '8px', paddingBottom: '8px' }}>
          {NAV_ITEMS.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              onClick={onClose}
              className={({ isActive }) => isActive ? active : inactive}
            >
              <Icon size={16} className="shrink-0" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </>
  )
}
