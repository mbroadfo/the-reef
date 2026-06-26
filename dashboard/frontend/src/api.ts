import type { Portfolio, Position, TradesResponse, Shark, Decision, Trade, Sentiment, Sector, MarketData, Nomination, AlphaData, ConvictionData } from './types'

const BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(/\/$/, '')

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

export const fetchSentiment = (): Promise<Sentiment> =>
  get<Sentiment>('/api/sentiment')

export const fetchSectors = (): Promise<Sector[]> =>
  get<Sector[]>('/api/sectors')

export const fetchMarket = (): Promise<MarketData> =>
  get<MarketData>('/api/market')

export const fetchNominations = (): Promise<Nomination[]> =>
  get<Nomination[]>('/api/nominations')

export const fetchAlpha = (): Promise<AlphaData> =>
  get<AlphaData>('/api/alpha')

export const fetchConviction = (): Promise<ConvictionData> =>
  get<ConvictionData>('/api/conviction')
