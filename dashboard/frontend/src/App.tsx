import { useState } from 'react'
import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import { PortfolioProvider } from './context/PortfolioContext'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import RightRail from './components/RightRail'
import MobileNav from './components/MobileNav'
import DashboardPage from './pages/DashboardPage'
import PositionsPage from './pages/PositionsPage'
import TradesPage from './pages/TradesPage'
import SharksPage from './pages/SharksPage'

const ComingSoon = () => (
  <div className="text-slate-500 p-8">Coming soon</div>
)

function AppShell() {
  const [navOpen, setNavOpen] = useState(false)
  const [, setLive] = useState(false)

  return (
    // Mobile: flex column. lg+: 3-column CSS grid.
    // gridColumn/gridRow on children are ignored when flex is active.
    <div
      className="h-screen w-screen overflow-hidden bg-reef-bg flex flex-col lg:grid lg:grid-rows-[88px_1fr]"
      style={{ gridTemplateColumns: '180px 1fr 460px' }}
    >
      {/* Sidebar — hidden on mobile, spans both rows on desktop */}
      <div
        className="hidden lg:flex lg:flex-col bg-reef-card border-r border-reef-border overflow-hidden"
        style={{ gridColumn: 1, gridRow: '1 / 3' }}
      >
        <Sidebar />
      </div>

      {/* TopBar — spans cols 2-3 on desktop, full width on mobile */}
      <div className="shrink-0" style={{ gridColumn: '2 / 4', gridRow: 1 }}>
        <TopBar onMenuClick={() => setNavOpen(true)} />
      </div>

      {/* Main content */}
      <main
        className="flex-1 overflow-y-auto p-4 lg:p-6 bg-reef-bg"
        style={{ gridColumn: 2, gridRow: 2 }}
      >
        <Outlet context={{ setLive }} />
      </main>

      {/* Right rail — hidden on mobile, visible on desktop */}
      <div className="hidden lg:block" style={{ gridColumn: 3, gridRow: 2 }}>
        <RightRail />
      </div>

      <MobileNav open={navOpen} onClose={() => setNavOpen(false)} />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <PortfolioProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/"          element={<DashboardPage onLive={() => {}} />} />
            <Route path="/sharks"    element={<SharksPage />} />
            <Route path="/positions" element={<PositionsPage />} />
            <Route path="/trades"    element={<TradesPage />} />
            <Route path="/trades/:id" element={<TradesPage />} />
            <Route path="/portfolio" element={<ComingSoon />} />
            <Route path="/market"    element={<ComingSoon />} />
            <Route path="/insights"  element={<ComingSoon />} />
            <Route path="/reports"   element={<ComingSoon />} />
            <Route path="/settings"  element={<ComingSoon />} />
          </Route>
        </Routes>
      </PortfolioProvider>
    </BrowserRouter>
  )
}
