import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Reef2Shell from './reef2/Reef2Shell'
import AquariumPage from './reef2/AquariumPage'
import ProposalPage from './reef2/ProposalPage'
import TeamPage from './reef2/TeamPage'
import LabPage from './reef2/LabPage'

// The Reef 1.0 dashboard (live API, portfolio and trade pages) was retired; it remains in git history.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Reef2Shell />}>
          <Route path="/"                 element={<AquariumPage />} />
          <Route path="/team/:id"         element={<TeamPage />} />
          <Route path="/proposal/:id"     element={<ProposalPage />} />
          <Route path="/lab"              element={<LabPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
