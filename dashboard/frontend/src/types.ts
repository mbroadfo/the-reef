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
  sector?: string
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
  sponsored_by?: string | null
  sponsor_bid?: number | null
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

export interface Holding {
  ticker: string
  daily_pct: number
  unrealized_pnl_pct: number
  market_value: number
  sector: string
}

export interface MarketData {
  vix: { current: number; previous: number; pct_change: number }
  holdings: Holding[]
}

export interface Nomination {
  ticker: string
  thesis: string
  source: string
  entry_range: string
  created_at: string
  expires_in_hours: number
  fresh: boolean
}

export interface ConvictionShark {
  shark_id: string
  points_remaining: number
  points_spent: number
  last_bid: { ticker: string; bid: number; direction: string } | null
}

export interface ConvictionData {
  date: string
  sharks: ConvictionShark[]
}

export interface AlphaSeries {
  date: string
  value: number
}

export interface AlphaData {
  reef_series: AlphaSeries[]
  spy_series: AlphaSeries[]
  alpha: number | null
  sharpe: number | null
  win_rate: number | null
  conviction_winners: number | null
  conviction_losers: number | null
  as_of: string
}
