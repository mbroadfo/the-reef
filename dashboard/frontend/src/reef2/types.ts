// Shape of public/reef2/snapshot.json, written by tools/build_competition_snapshot.py from the ledger.
export interface LedgerEventJson {
  seq: number
  prev_hash: string
  hash: string
  event_id: string
  epoch_id: string
  kind: string
  occurred_at: string
  payload: Record<string, unknown>
}

export interface Metric { label: string; value: string }
export interface FindingJson { agent: string; role: string; verdict: string; summary: string; metrics: Metric[] }

export interface Packet {
  proposal_id: string
  pod_id: string
  symbol: string
  intent: string
  sector: string | null
  thesis: string
  findings: FindingJson[]
  rationale: string
  created_at: string
  as_of_session: string
  score: string
  entry_plan: { type: string; reference_price: string; reference: string }
  exit_plan: { stop_price: string; rules: string[] }
  risk: { risk_per_share: string; stop_distance_pct: string; risk_at_request: string }
  capital_request: { dollars: string; shares: number; fraction_of_sleeve_cash: string }
  strategy: string
}

export interface Decision {
  seq: number
  outcome: 'FUNDED' | 'DECLINED'
  rule: string
  rank: number
  of: number
  reasons: string[]
  detail: string
  sleeve_cash: string
  max_new_per_session: number
  requested_shares?: number
  ceiling_shares?: number
  granted_shares?: number
  ceiling_dollars?: string
  granted_dollars?: string
  risk_check_shares?: number | null
  order_id?: string
  fill_session?: string
}

export interface Lifecycle {
  status: 'OPEN' | 'CLOSED' | 'NOT_FILLED'
  reason?: string
  entry?: { seq: number; session_day: string; price: string; shares: number; cost: string }
  stop_raises?: { seq: number; stop_price: string }[]
  exit?: { seq: number; session_day: string; price: string; shares: number; reason: string | null } | null
  pnl?: string | null
  return?: number | null
  sleeve_return_contribution?: number | null
  fund_return_contribution?: number | null
  sleeve_nav_before?: string | null
  sleeve_nav_after?: string | null
  price_path?: [string, string][]
}

export interface ProposalRow {
  proposal_id: string
  pod_id: string
  symbol: string
  as_of_session: string
  packet: Packet
  packet_seq: number
  decision: Decision | null
  decision_explained: string[]
  order?: { order_id: string; status: string; fill_session: string; requested_shares: number; stop_price: string | null; seq: number }
  lifecycle?: Lifecycle
  counterfactual?: { hypothetical: true; ref_price: string; last_close: string; move: number; through: string }
}

export interface PositionRow { symbol: string; shares: number; avg_cost: string; mark: string; stop: string | null; unrealized: string }

export interface Pod {
  pod_id: string
  name: string
  tagline: string
  mandate: string
  color: string
  status: 'ACTIVE' | 'INACTIVE'
  inactive_reason: string
  research_agents: string[]
  sleeve_weight: string
  // ACTIVE pods only
  funded?: string
  nav?: string
  cash?: string
  invested?: string
  realized_pnl?: string
  unrealized_pnl?: string
  positions?: PositionRow[]
  nav_series?: [string, string][]
  return?: number
  max_drawdown?: number
  sessions?: number
  volatility_ann?: number | null
  sharpe_like?: number | null
  return_over_drawdown?: number | null
  trades?: number
  win_rate?: number | null
  avg_win?: string | null
  avg_loss?: string | null
  avg_exposure?: number
  proposals?: number
  funded_proposals?: number
  strategy?: string
  rank?: number
}

export interface Snapshot {
  schema_version: number
  mode: { kind: string; label: string; disclosure: string }
  generated_from: { epoch_id: string; events: number; head_hash: string; first_session: string; last_session: string; initial_cash: string }
  limits: Record<string, string>
  apex: { allocator: string; sleeve_weights: Record<string, string>; max_new_positions_per_pod_per_session: number; rule: string }
  fund: {
    nav: string; unallocated: string; return: number; max_drawdown: number
    nav_series: [string, string][]
    benchmark: { name: string; series: [string, string][]; return: number | null }
  }
  pods: Pod[]
  proposals: ProposalRow[]
  prices: Record<string, [string, string][]>
  checks: { name: string; ok: boolean; detail: string }[]
  events: LedgerEventJson[]
}
