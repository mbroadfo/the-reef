import { Link, NavLink, Outlet } from 'react-router-dom'
import reefLogo from '../assets/the_reef_logo.png'
import { useSnapshot } from './useSnapshot'

const link = 'px-3 py-1.5 rounded-full text-sm font-medium transition-colors'
const on = `${link} bg-cyan-400/15 text-cyan-200`
const off = `${link} text-slate-400 hover:text-white hover:bg-white/5`

const BUBBLES = [
  { left: '6%', size: 8, dur: 16, delay: 0 }, { left: '19%', size: 5, dur: 22, delay: 6 }, { left: '33%', size: 11, dur: 19, delay: 3 },
  { left: '52%', size: 6, dur: 24, delay: 9 }, { left: '71%', size: 9, dur: 18, delay: 2 }, { left: '88%', size: 5, dur: 21, delay: 11 },
]

export default function Reef2Shell() {
  const { snap } = useSnapshot()
  return (
    <div className="tank-bg min-h-screen relative overflow-x-hidden" style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
      <div aria-hidden className="absolute inset-x-0 top-0 h-[520px] overflow-hidden pointer-events-none">
        {BUBBLES.map((b, i) => (
          <span key={i} className="bubble" style={{ left: b.left, width: b.size, height: b.size, animationDuration: `${b.dur}s`, animationDelay: `${b.delay}s`, top: 'auto', bottom: 0 }} />
        ))}
      </div>

      {/* Honest labelling comes first, on every page. */}
      <div role="status" className="relative z-20 flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 text-xs"
           style={{ background: 'rgba(245,158,11,0.14)', borderBottom: '1px solid rgba(245,158,11,0.45)', color: '#e2e8f0' }}>
        <span className="font-extrabold tracking-[0.12em] text-amber-400 whitespace-nowrap">{(snap?.mode.label ?? 'FIXTURE DEMONSTRATION').toUpperCase()}</span>
        <span className="text-slate-300">{snap?.mode.disclosure ?? 'Synthetic prices through the real engine. Not live, not real money.'}</span>
      </div>

      <header className="relative z-10 mx-auto max-w-6xl px-4 pt-4 flex flex-wrap items-center gap-3">
        <Link to="/" className="flex items-center gap-3 mr-auto">
          <img src={reefLogo} alt="The Reef" style={{ height: 44, width: 'auto', filter: 'brightness(1.4) drop-shadow(0 0 6px rgba(0,255,136,0.3))' }} />
          <div className="leading-tight">
            <div className="text-lg font-bold tracking-wide text-white">THE REEF</div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-300/80">Shark competition</div>
          </div>
        </Link>
        <nav className="flex items-center gap-1" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => (isActive ? on : off)}>Aquarium</NavLink>
          <NavLink to="/lab" className={({ isActive }) => (isActive ? on : off)}>Research Lab</NavLink>
          <NavLink to="/dashboard" className={off}>Legacy dashboard</NavLink>
        </nav>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-16 pt-5">
        <Outlet />
      </main>

      <footer className="relative z-10 mx-auto max-w-6xl px-4 pb-10 text-xs text-slate-500 leading-relaxed">
        <p>
          Ideas adopted, no code copied: independent investor-persona agents with a portfolio manager on top
          (<a className="underline" href="https://github.com/virattt/ai-hedge-fund">virattt/ai-hedge-fund</a>); role-structured research
          feeding a trader and an independent risk check (<a className="underline" href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a>);
          a layered, agent-oriented financial platform with data and decision layers kept separate
          (<a className="underline" href="https://github.com/AI4Finance-Foundation/FinRobot">AI4Finance-Foundation/FinRobot</a>).
        </p>
      </footer>
    </div>
  )
}
