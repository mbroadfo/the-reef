import type { Portfolio, Position, TradesResponse, Shark, Decision, Trade } from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const fetchPortfolio = (): Promise<Portfolio> =>
  get<Portfolio>('/api/portfolio')

export const fetchPositions = (): Promise<Position[]> =>
  get<Position[]>('/api/positions')

export const fetchTrades = (limit = 50, skip = 0): Promise<TradesResponse> =>
  get<TradesResponse>(`/api/trades?limit=${limit}&skip=${skip}`)

export const fetchTradeDetail = (id: number): Promise<Trade> =>
  get<Trade>(`/api/trades/${id}`)

export const fetchSharks = (): Promise<Shark[]> =>
  get<Shark[]>('/api/sharks')

export const fetchDecisions = (): Promise<Decision[]> =>
  get<Decision[]>('/api/decisions')
