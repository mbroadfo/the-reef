// Session-by-session replay of the competition. Every view is derived from the ledger events up to the close of
// the chosen session (plus point-in-time prices up to that day) and from nothing else, so a view of session 12
// cannot contain anything that happened in session 13. Pod metadata (names, mandates) is static and carries no results.
import type { Decision, LedgerEventJson, Packet, Pod, Snapshot } from './types.ts'

export interface SessionRef { index: number; day: string; markedSeq: number; closedSeq: number }

export type PitchState = 'DECLINED' | 'QUEUED' | 'NOT_FILLED' | 'OPEN' | 'CLOSED'

export interface PitchView {
  proposal_id: string
  pod_id: string
  symbol: string
  as_of_session: string
  packet: Packet
  packet_seq: number
  decision: (Decision & { sleeve_id?: string }) | null
  decision_explained: string[]
  state: PitchState
  entry?: { seq: number; session_day: string; price: number; shares: number }
  exit?: { seq: number; session_day: string; price: number; reason: string }
  stop?: number | null
  mark?: number | null
  pnl?: number | null            // realized once closed, otherwise unrealized at the latest official close
  position_return?: number | null
  decided_today: boolean
  sessions_held?: number
}

export interface PositionNow { symbol: string; shares: number; avg_cost: number; mark: number; stop: number | null; unrealized: number; entry_day: string; sessions_held: number }

export interface CapitalTransfer { sleeve_id: string; amount: number; counterparty: string; seq: number | null }
export interface CapitalEvidence {
  history_sessions: number; window_sessions: number; window_return: number; window_max_drawdown: number; score: number
  lifetime_return: number; proposals: number; funded_proposals: number; closed_trades: number; win_rate: number | null
  sleeve_nav: number; sleeve_cash: number; committed_cash: number; free_cash: number; utilization: number
  net_capital: number; initial_funding: number
}
// One Apex capital review, exactly as the ledger recorded it (APEX_CAPITAL_DECISION plus the SLEEVE_FUNDED events it ordered).
export interface CapitalReview {
  review_id: string
  review_no: number              // marked sessions at the review
  index: number                  // 0-based session of the review
  day: string
  seq: number
  outcome: 'REALLOCATED' | 'HELD'
  reasons: string[]
  rationale: string
  leader: string | null
  trailer: string | null
  gap: number | null
  fund_nav: number
  reserve_before: number
  reserve_after: number
  transfers: CapitalTransfer[]
  evidence: Record<string, CapitalEvidence>
  decided_today: boolean
}
export interface CapitalPoint { day: string; pods: Record<string, number>; reserve: number }

export interface PodView {
  pod_id: string
  funded: number                 // net capital ever contributed: initial funding plus transfers
  initial_funded: number
  net_transfers: number          // capital moved in (+) or out (-) by Apex; never a return
  controlled: number             // capital the pod controls right now: its NAV plus any transfer made at this close
  pnl: number                    // investment P&L: realized plus unrealized, unaffected by transfers
  twr_series: [string, number][] // capital-flow-adjusted growth of 1
  nav: number
  cash: number
  invested: number
  realized: number
  unrealized: number
  return: number
  max_drawdown: number
  sessions: number
  volatility_ann: number | null
  sharpe_like: number | null
  trades: number
  wins: number
  win_rate: number | null
  avg_win: number | null
  avg_loss: number | null
  avg_exposure: number
  avg_hold: number | null          // sessions held, closed trades
  stop_exits: number
  rule_exits: number
  proposals: number
  funded_proposals: number
  positions: PositionNow[]
  nav_series: [string, number][]
  rank: number
  lead_by_return: boolean
}

export interface SessionView {
  index: number                      // 0-based
  total: number
  day: string
  cutSeq: number
  headHash: string
  eventsVisible: number
  fundNav: number
  fundReturn: number
  fundSeries: [string, number][]
  benchSeries: [string, number][]
  benchReturn: number | null
  pods: PodView[]                    // active pods only
  pitches: PitchView[]               // every pitch known by this session's close, oldest first
  reviews: CapitalReview[]           // every capital review known by this session's close, oldest first
  reviewsToday: CapitalReview[]
  capital: CapitalPoint[]            // capital by session (marked NAVs) up to this session
  reserve: number                    // central reserve after any transfer made at this close
  today: PitchView[]                 // pitches decided at this session's close
  prices: Record<string, [string, number][]>
}

const num = (v: unknown): number => Number(v)

export function sessionsOf(events: LedgerEventJson[]): SessionRef[] {
  const out: SessionRef[] = []
  let marked: { day: string; seq: number } | null = null
  for (const e of events) {
    if (e.kind === 'SESSION_MARKED') marked = { day: String((e.payload as any).session_day), seq: e.seq }
    else if (e.kind === 'SESSION_CLOSED' && marked) {
      out.push({ index: out.length, day: marked.day, markedSeq: marked.seq, closedSeq: e.seq })
      marked = null
    }
  }
  return out
}

export function seriesStats(navs: number[], base: number) {
  const vals = [base, ...navs]
  const rets: number[] = []
  for (let i = 1; i < vals.length; i++) if (vals[i - 1] > 0) rets.push(vals[i] / vals[i - 1] - 1)
  const n = rets.length
  const mean = n ? rets.reduce((a, b) => a + b, 0) / n : 0
  const sd = n > 1 ? Math.sqrt(rets.reduce((a, r) => a + (r - mean) ** 2, 0) / (n - 1)) : 0
  let peak = base, worst = 0
  for (const v of navs) { peak = Math.max(peak, v); worst = Math.min(worst, v / peak - 1) }
  return {
    ret: base > 0 ? vals[vals.length - 1] / base - 1 : 0,
    max_drawdown: worst,
    sessions: n,
    volatility_ann: sd ? sd * Math.sqrt(252) : null,
    sharpe_like: sd ? (mean / sd) * Math.sqrt(252) : null,
  }
}

// Time-weighted statistics from flow-adjusted per-session returns (mirrors the_reef/aquarium/snapshot.py::_stats).
export function flowStats(rets: number[]) {
  const n = rets.length
  const mean = n ? rets.reduce((a, b) => a + b, 0) / n : 0
  const sd = n > 1 ? Math.sqrt(rets.reduce((a, r) => a + (r - mean) ** 2, 0) / (n - 1)) : 0
  let idx = 1, peak = 1, worst = 0
  for (const r of rets) { idx *= 1 + r; peak = Math.max(peak, idx); worst = Math.min(worst, idx / peak - 1) }
  return {
    ret: idx - 1, max_drawdown: worst, sessions: n,
    volatility_ann: sd ? sd * Math.sqrt(252) : null,
    sharpe_like: sd ? (mean / sd) * Math.sqrt(252) : null,
  }
}

interface Pos { shares: number; cost: number; stop: number | null; entryDay: string; entryIdx: number }

export function viewAt(snap: Snapshot, index: number): SessionView {
  const sessions = sessionsOf(snap.events)
  const idx = Math.max(0, Math.min(index, sessions.length - 1))
  const ref = sessions[idx]
  const cut = ref.closedSeq
  const events = snap.events.filter(e => e.seq <= cut)          // the only source of results below
  const dayIdx = new Map(sessions.map(s => [s.day, s.index]))
  const activeIds = snap.pods.filter(p => p.status === 'ACTIVE').map(p => p.pod_id)

  const cash: Record<string, number> = {}
  const funded: Record<string, number> = {}
  const realized: Record<string, number> = {}
  const book: Record<string, Record<string, Pos>> = {}
  const navSeries: Record<string, [string, number][]> = {}
  const exposure: Record<string, number[]> = {}
  const pending: Record<string, number> = {}                  // transfers since the last mark
  const lastNav: Record<string, number> = {}
  const rets: Record<string, number[]> = {}
  const twr: Record<string, [string, number][]> = {}
  const capital: CapitalPoint[] = []
  const initialFunding: Record<string, number> = {}
  const reviewRaw: { seq: number; p: Record<string, any> }[] = []
  const reviewFunding = new Map<string, { sleeve_id: string; amount: number; seq: number }[]>()
  const trades: Record<string, { pnl: number; held: number; stop: boolean }[]> = {}
  let marks: Record<string, number> = {}
  const fundSeries: [string, number][] = []
  const packets = new Map<string, { packet: Packet; seq: number }>()
  const decisions = new Map<string, Decision & { sleeve_id?: string }>()
  const orders = new Map<string, { seq: number; rationale: string }>()
  const rejected = new Set<string>()
  const fills: { seq: number; sleeve: string; symbol: string; side: string; shares: number; price: number; order_id: string; day: string; stop: number | null }[] = []
  const stopMoves: { seq: number; sleeve: string; symbol: string; stop: number }[] = []
  let head = ''

  for (const e of events) {
    head = e.hash
    const p = e.payload as Record<string, any>
    switch (e.kind) {
      case 'SLEEVE_FUNDED':
        cash[p.sleeve_id] = (cash[p.sleeve_id] ?? 0) + num(p.amount)
        funded[p.sleeve_id] = (funded[p.sleeve_id] ?? 0) + num(p.amount)
        pending[p.sleeve_id] = (pending[p.sleeve_id] ?? 0) + num(p.amount)
        if (p.ref === 'd0-initial') initialFunding[p.sleeve_id] = num(p.amount)
        else reviewFunding.set(String(p.ref), [...(reviewFunding.get(String(p.ref)) ?? []), { sleeve_id: p.sleeve_id, amount: num(p.amount), seq: e.seq }])
        break
      case 'APEX_CAPITAL_DECISION':
        reviewRaw.push({ seq: e.seq, p })
        break
      case 'PROPOSAL_SUBMITTED':
        packets.set(p.proposal_id, { packet: p as Packet, seq: e.seq })
        break
      case 'APEX_DECISION':
        decisions.set(p.proposal_id, { ...(p as Decision), seq: e.seq })
        break
      case 'ORDER_QUEUED':
        orders.set(p.order_id, { seq: e.seq, rationale: String(p.rationale ?? '') })
        break
      case 'ORDER_REJECTED':
        rejected.add(p.order_id)
        break
      case 'STOP_UPDATED': {
        stopMoves.push({ seq: e.seq, sleeve: p.sleeve_id, symbol: p.symbol, stop: num(p.stop_price) })
        const pos = book[p.sleeve_id]?.[p.symbol]
        if (pos) pos.stop = num(p.stop_price)
        break
      }
      case 'FILL': {
        const sid: string = p.sleeve_id
        const px = num(p.price), n = num(p.shares)
        const sleeve = (book[sid] ??= {})
        fills.push({ seq: e.seq, sleeve: sid, symbol: p.symbol, side: p.side, shares: n, price: px, order_id: String(p.order_id), day: String(p.session_day), stop: p.stop_price == null ? null : num(p.stop_price) })
        if (p.side === 'BUY') {
          const pos = (sleeve[p.symbol] ??= { shares: 0, cost: 0, stop: null, entryDay: String(p.session_day), entryIdx: dayIdx.get(String(p.session_day)) ?? idx })
          pos.shares += n; pos.cost += px * n
          if (p.stop_price != null) pos.stop = num(p.stop_price)
          cash[sid] -= px * n
        } else {
          const pos = sleeve[p.symbol]
          const removed = pos.cost * n / pos.shares
          realized[sid] = (realized[sid] ?? 0) + px * n - removed
          pos.shares -= n; pos.cost -= removed; cash[sid] += px * n
          if (pos.shares === 0) {
            ;(trades[sid] ??= []).push({ pnl: px * n - removed, held: (dayIdx.get(String(p.session_day)) ?? idx) - pos.entryIdx, stop: String(p.order_id).startsWith('stop:') })
            delete sleeve[p.symbol]
          }
        }
        break
      }
      case 'SESSION_MARKED': {
        marks = Object.fromEntries(Object.entries(p.marks as Record<string, string>).map(([k, v]) => [k, num(v)]))
        fundSeries.push([String(p.session_day), num(p.nav)])
        const sleeveNavs = Object.fromEntries(Object.entries(p.sleeve_nav as Record<string, string>).map(([k, v]) => [k, num(v)]))
        capital.push({ day: String(p.session_day), pods: sleeveNavs, reserve: num(p.nav) - Object.values(sleeveNavs).reduce((a, b) => a + b, 0) })
        for (const [sid, nav] of Object.entries(p.sleeve_nav as Record<string, string>)) {
          ;(navSeries[sid] ??= []).push([String(p.session_day), num(nav)])
          const base = (lastNav[sid] ?? 0) + (pending[sid] ?? 0)
          const r = base > 0 ? num(nav) / base - 1 : 0
          ;(rets[sid] ??= []).push(r)
          ;(twr[sid] ??= []).push([String(p.session_day), (twr[sid]?.length ? twr[sid][twr[sid].length - 1][1] : 1) * (1 + r)])
          lastNav[sid] = num(nav); pending[sid] = 0
          if (num(nav) > 0) (exposure[sid] ??= []).push((num(nav) - cash[sid]) / num(nav))
        }
        break
      }
    }
  }

  // ---- pitches --------------------------------------------------------------------------------------------
  const explained = new Map(snap.proposals.map(r => [r.proposal_id, r.decision_explained]))
  const pitches: PitchView[] = []
  for (const [pid, { packet, seq }] of packets) {
    const dec = decisions.get(pid) ?? null
    const v: PitchView = {
      proposal_id: pid, pod_id: packet.pod_id, symbol: packet.symbol, as_of_session: packet.as_of_session, packet, packet_seq: seq,
      decision: dec, decision_explained: dec ? (explained.get(pid) ?? []) : [], state: 'DECLINED',
      decided_today: !!dec && dec.seq > (idx > 0 ? sessions[idx - 1].closedSeq : 0),
    }
    if (dec && dec.outcome === 'FUNDED' && dec.order_id) {
      const entry = fills.find(f => f.sleeve === packet.pod_id && f.order_id === dec.order_id)
      if (!entry) v.state = rejected.has(dec.order_id) ? 'NOT_FILLED' : 'QUEUED'
      else {
        v.entry = { seq: entry.seq, session_day: entry.day, price: entry.price, shares: entry.shares }
        const exit = fills.find(f => f.sleeve === packet.pod_id && f.symbol === packet.symbol && f.side === 'SELL' && f.seq > entry.seq)
        const moves = stopMoves.filter(s => s.sleeve === packet.pod_id && s.symbol === packet.symbol && s.seq > entry.seq && (!exit || s.seq < exit.seq))
        v.stop = moves.length ? moves[moves.length - 1].stop : (entry.stop ?? num(packet.exit_plan.stop_price))
        const endIdx = exit ? (dayIdx.get(exit.day) ?? idx) : idx
        v.sessions_held = endIdx - (dayIdx.get(entry.day) ?? idx)
        if (exit) {
          v.state = 'CLOSED'
          const queued = orders.get(exit.order_id)
          v.exit = { seq: exit.seq, session_day: exit.day, price: exit.price,
                     reason: exit.order_id.startsWith('stop:') ? 'Stopped out: the price fell to its protective stop' : 'Strategy exit: ' + (queued?.rationale.split('] ').slice(1).join('] ') || 'exit rule') }
          v.pnl = (exit.price - entry.price) * entry.shares
          v.position_return = exit.price / entry.price - 1
        } else {
          v.state = 'OPEN'
          v.mark = marks[packet.symbol] ?? null
          v.pnl = v.mark == null ? null : (v.mark - entry.price) * entry.shares
          v.position_return = v.mark == null ? null : v.mark / entry.price - 1
        }
      }
    }
    pitches.push(v)
  }

  // ---- pods -----------------------------------------------------------------------------------------------
  const base = activeIds.map(id => {
    const series = navSeries[id] ?? []
    const f = funded[id] ?? 0
    const st = flowStats(rets[id] ?? [])
    const tr = trades[id] ?? []
    const wins = tr.filter(t => t.pnl > 0).length
    const positions: PositionNow[] = Object.entries(book[id] ?? {}).filter(([, p]) => p.shares > 0).sort(([a], [b]) => a.localeCompare(b)).map(([sym, p]) => {
      const mark = marks[sym] ?? p.cost / p.shares
      return { symbol: sym, shares: p.shares, avg_cost: p.cost / p.shares, mark, stop: p.stop, unrealized: mark * p.shares - p.cost, entry_day: p.entryDay, sessions_held: idx - p.entryIdx }
    })
    const unreal = positions.reduce((a, p) => a + p.unrealized, 0)
    const nav = series.length ? series[series.length - 1][1] : f
    const ex = exposure[id] ?? []
    const mine = pitches.filter(p => p.pod_id === id)
    return {
      pod_id: id, funded: f, initial_funded: initialFunding[id] ?? 0, net_transfers: f - (initialFunding[id] ?? 0),
      controlled: nav + (pending[id] ?? 0), pnl: (realized[id] ?? 0) + unreal, twr_series: twr[id] ?? [],
      nav, cash: cash[id] ?? 0, invested: nav + (pending[id] ?? 0) - (cash[id] ?? 0), realized: realized[id] ?? 0, unrealized: unreal,
      return: st.ret, max_drawdown: st.max_drawdown, sessions: st.sessions, volatility_ann: st.volatility_ann, sharpe_like: st.sharpe_like,
      trades: tr.length, wins, win_rate: tr.length ? wins / tr.length : null,
      avg_win: wins ? tr.filter(t => t.pnl > 0).reduce((a, t) => a + t.pnl, 0) / wins : null,
      avg_loss: tr.length > wins ? tr.filter(t => t.pnl <= 0).reduce((a, t) => a + t.pnl, 0) / (tr.length - wins) : null,
      avg_exposure: ex.length ? ex.reduce((a, b) => a + b, 0) / ex.length : 0,
      avg_hold: tr.length ? tr.reduce((a, t) => a + t.held, 0) / tr.length : null,
      stop_exits: tr.filter(t => t.stop).length, rule_exits: tr.filter(t => !t.stop).length,
      proposals: mine.length, funded_proposals: mine.filter(p => p.decision?.outcome === 'FUNDED').length,
      positions, nav_series: series, rank: 0, lead_by_return: false as boolean,
    } satisfies PodView
  })
  const ranked = [...base].sort((a, b) => (-(a.sharpe_like ?? -9e9) + (b.sharpe_like ?? -9e9)) || (b.return - a.return))
  ranked.forEach((p, i) => { p.rank = i + 1 })
  const topReturn = Math.max(...base.map(p => p.return))
  base.forEach(p => { p.lead_by_return = base.length > 1 && p.return === topReturn && base.filter(q => q.return === topReturn).length === 1 })

  const reviews: CapitalReview[] = reviewRaw.map(({ seq, p }) => {
    const funding = reviewFunding.get(String(p.review_id)) ?? []
    const at = sessions.findIndex(x => x.closedSeq >= seq)
    return {
      review_id: String(p.review_id), review_no: Number(p.review_no), index: at, day: String(p.session_day), seq,
      outcome: p.outcome, reasons: p.reasons ?? [], rationale: String(p.rationale), leader: p.leader ?? null, trailer: p.trailer ?? null,
      gap: p.gap == null ? null : num(p.gap), fund_nav: num(p.fund_nav), reserve_before: num(p.reserve_before), reserve_after: num(p.reserve_after),
      transfers: (p.transfers as any[]).map(t => ({ sleeve_id: t.sleeve_id, amount: num(t.amount), counterparty: String(t.counterparty),
                                                     seq: funding.find(f => f.sleeve_id === t.sleeve_id && f.amount === num(t.amount))?.seq ?? null })),
      evidence: Object.fromEntries(Object.entries(p.evidence as Record<string, any>).map(([k, v]) => [k, {
        history_sessions: v.history_sessions, window_sessions: v.window_sessions, window_return: num(v.window_return), window_max_drawdown: num(v.window_max_drawdown),
        score: num(v.score), lifetime_return: num(v.lifetime_return), proposals: v.proposals, funded_proposals: v.funded_proposals, closed_trades: v.closed_trades,
        win_rate: v.win_rate == null ? null : num(v.win_rate), sleeve_nav: num(v.sleeve_nav), sleeve_cash: num(v.sleeve_cash), committed_cash: num(v.committed_cash),
        free_cash: num(v.free_cash), utilization: num(v.utilization), net_capital: num(v.net_capital), initial_funding: num(v.initial_funding),
      } as CapitalEvidence])),
      decided_today: at === idx,
    }
  })
  const controlledTotal = base.reduce((a, p) => a + p.controlled, 0)

  const symbols = new Set(pitches.map(p => p.symbol))
  const prices: Record<string, [string, number][]> = {}
  for (const s of symbols) prices[s] = (snap.prices[s] ?? []).filter(([d]) => d <= ref.day).map(([d, c]) => [d, num(c)])
  const bench = snap.fund.benchmark.series.filter(([d]) => d <= ref.day).map(([d, v]) => [d, num(v)] as [string, number])
  const initial = num(snap.generated_from.initial_cash)
  const fundNav = fundSeries.length ? fundSeries[fundSeries.length - 1][1] : initial

  return {
    index: idx, total: sessions.length, day: ref.day, cutSeq: cut, headHash: head, eventsVisible: events.length,
    fundNav, fundReturn: fundNav / initial - 1, fundSeries, benchSeries: bench,
    benchReturn: bench.length ? bench[bench.length - 1][1] / initial - 1 : null,
    pods: base, pitches, today: pitches.filter(p => p.decided_today), prices,
    reviews, reviewsToday: reviews.filter(r => r.decided_today), capital, reserve: fundNav - controlledTotal,
  }
}

// The one pitch to feature at a session: a fresh funded decision if there is one, else a fresh decline that
// is not a repeat refusal, else the most recent funded decision, else nothing.
export function spotlightFor(view: SessionView): { pitch: PitchView; fresh: boolean } | null {
  const repeat = (p: PitchView) => !!p.decision && p.decision.outcome === 'DECLINED' && !p.decision.reasons.includes('D0_RANK_CAP')
  const fresh = view.today.find(p => p.decision?.outcome === 'FUNDED') ?? view.today.find(p => !repeat(p))
  if (fresh) return { pitch: fresh, fresh: true }
  const last = [...view.pitches].reverse().find(p => p.decision?.outcome === 'FUNDED') ?? [...view.pitches].reverse()[0]
  return last ? { pitch: last, fresh: false } : null
}

// Pod metadata lookups used by the views; never carries results.
export const podMeta = (snap: Snapshot, id: string): Pod => snap.pods.find(p => p.pod_id === id)!

export interface Marker { index: number; pod_id: string; symbol: string; proposal_id: string; funded: boolean }

// Where decisions fall on the timeline: every funded decision, and the first of each distinct decline (so a pitch that
// is refused again every session for the same reason shows once). Positions are decision dates, which are public.
export function decisionMarkers(snap: Snapshot): Marker[] {
  const sessions = sessionsOf(snap.events)
  const packets = new Map<string, Packet>()
  const seen = new Set<string>()
  const out: Marker[] = []
  for (const e of snap.events) {
    const p = e.payload as Record<string, any>
    if (e.kind === 'PROPOSAL_SUBMITTED') packets.set(p.proposal_id, p as Packet)
    if (e.kind !== 'APEX_DECISION') continue
    const pk = packets.get(p.proposal_id)!
    const index = sessions.findIndex(s => s.closedSeq >= e.seq)
    const funded = p.outcome === 'FUNDED'
    const reasons: string[] = p.reasons ?? []
    const key = `${pk.pod_id}|${pk.symbol}|${reasons.join('+')}`
    const repeatable = !funded && !reasons.includes('D0_RANK_CAP')
    if (repeatable && seen.has(key)) continue
    seen.add(key)
    out.push({ index, pod_id: pk.pod_id, symbol: pk.symbol, proposal_id: p.proposal_id, funded })
  }
  return out
}

export interface CapitalMarker { index: number; review_id: string; moved: boolean }

// Where capital reviews fall on the timeline. Like pitches, they are dated by the session in which they were decided.
export function capitalMarkers(snap: Snapshot): CapitalMarker[] {
  const sessions = sessionsOf(snap.events)
  return snap.events.filter(e => e.kind === 'APEX_CAPITAL_DECISION').map(e => {
    const p = e.payload as Record<string, any>
    return { index: sessions.findIndex(s => s.closedSeq >= e.seq), review_id: String(p.review_id), moved: p.outcome === 'REALLOCATED' }
  })
}
