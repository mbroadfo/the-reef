import { useState, useCallback } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Nav from './components/Nav'
import DashboardPage from './pages/DashboardPage'
import PositionsPage from './pages/PositionsPage'
import TradesPage from './pages/TradesPage'
import SharksPage from './pages/SharksPage'

export default function App() {
  const [live, setLive] = useState(false)
  const onLive = useCallback((v: boolean) => setLive(v), [])

  return (
    <BrowserRouter>
      <Nav live={live} />
      <main>
        <Routes>
          <Route path="/" element={<DashboardPage onLive={onLive} />} />
          <Route path="/positions" element={<PositionsPage />} />
          <Route path="/trades" element={<TradesPage />} />
          <Route path="/trades/:id" element={<TradesPage />} />
          <Route path="/sharks" element={<SharksPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
