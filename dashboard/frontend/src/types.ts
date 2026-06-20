export interface Snapshot {
  timestamp: string
  portfolio_value: number
  cash: number
  equity: number
  event: string
}

export interface Portfolio {
  value: number
  cash: number
  equity: number
  starting_cash: number
  total_pnl: number
  total_pnl_pct: number
  realized_pnl: number
  unrealized_pnl: number
  win_rate_pct: number
  total_trades: number
  wins: number
  losses: number
  profit_factor: number | null
  snapshots: Snapshot[]
  today_gain?: number
  today_gain_pct?: number
  month_gain?: number
  month_gain_pct?: number
  active_sharks?: number
  inception_date?: string
  max_trade_gain?: number
  max_drawdown?: number
}

export interface Position {
  ticker: string
  shares: number
  entry_price: number
  current_price: number
  stop_loss: number | null
  target_price: number | null
  unrealized_pnl: number
  unrealized_pnl_pct: number
  cost_basis: number
  market_value: number
  surfaced_by: string
  vetted_by: string
  conviction: number
  entry_time: string
}

export interface Trade {
  id: number
  ticker: string
  action: 'BUY' | 'SELL'
  shares: number
  price: number
  timestamp: string
  surfaced_by: string
  vetted_by: string
  conviction: number
  stop_loss: number | null
  target_price: number | null
  reason: string
  outcome: string
  pnl: number | null
  exit_price: number | null
  exit_time: string | null
  apex_rationale?: string
  apex_decision?: string
  apex_conviction?: number
}

export interface TradesResponse {
  trades: Trade[]
  total: number
  skip: number
  limit: number
}

export interface Shark {
  name: string
  trades: number
  total_pnl: number
  avg_pnl: number
  win_rate: number
}

export interface Decision {
  ticker: string
  signal_type: string
  decision: string
  conviction: number
  rationale: string
  timestamp: string
}

export interface Sentiment {
  score: number
  label: 'Bullish' | 'Neutral' | 'Bearish'
  components: {
    win_rate: number
    trend: number
    positions: number
  }
}

export interface Sector {
  sector: string
  ticker: string
  pct_change: number
}
