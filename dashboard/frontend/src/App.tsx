import { useState } from 'react'
import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import { PortfolioProvider } from './context/PortfolioContext'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import RightRail from './components/RightRail'
import DashboardPage from './pages/DashboardPage'
import PositionsPage from './pages/PositionsPage'
import TradesPage from './pages/TradesPage'
import SharksPage from './pages/SharksPage'

const ComingSoon = () => (
  <div className="text-slate-500 p-8">Coming soon</div>
)

function AppShell() {
  const [, setLive] = useState(false)

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '180px 841px 1fr',
      gridTemplateRows: '64px 1fr',
      height: '100vh',
      width: '100vw',
      overflow: 'hidden',
      background: 'var(--reef-bg)',
    }}>
      <Sidebar />
      <TopBar />
      <main
        className="overflow-y-auto p-6 bg-reef-bg"
        style={{ gridColumn: '2', gridRow: '2' }}
      >
        <Outlet context={{ setLive }} />
      </main>
      <RightRail />
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
