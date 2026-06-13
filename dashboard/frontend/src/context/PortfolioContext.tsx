import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { fetchPortfolio } from '../api'
import type { Portfolio } from '../types'

const PortfolioContext = createContext<Portfolio | null>(null)

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)

  useEffect(() => {
    const load = () => fetchPortfolio().then(setPortfolio).catch(() => {})
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <PortfolioContext.Provider value={portfolio}>
      {children}
    </PortfolioContext.Provider>
  )
}

export function usePortfolio() {
  return useContext(PortfolioContext)
}
