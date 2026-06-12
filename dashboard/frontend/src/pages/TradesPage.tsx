import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchTrades, fetchTradeDetail } from '../api'
import type { Trade, TradesResponse } from '../types'
import TradesTable from '../components/TradesTable'
import SharkAvatar from '../components/SharkAvatar'
import ConvictionBar from '../components/ConvictionBar'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function TradeDetail({ id }: { id: number }) {
  const [trade, setTrade] = useState<Trade | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchTradeDetail(id).then(setTrade)
  }, [id])

  if (!trade) return <div className="text-slate-500 text-sm animate-pulse">Loading...</div>

  const isBuy    = trade.action === 'BUY'
  const pnlPos   = (trade.pnl ?? 0) >= 0
  const sharkName = normalizeSharkName(trade.surfaced_by || 'Apex Shark')
  const color    = getSharkColor(sharkName)

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
      <button
        onClick={() => navigate('/trades')}
        className="text-slate-500 hover:text-white text-xs font-sans transition-colors"
      >
        ← Back to Trades
      </button>

      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-4">
          <SharkAvatar name={trade.surfaced_by} size="lg" />
          <div>
            <div className="flex items-center gap-3">
              <span className={`text-2xl font-bold font-mono ${isBuy ? 'text-blue-400' : 'text-amber-400'}`}>
                {trade.action}
              </span>
              <span className="text-2xl font-bold font-mono text-white">{trade.ticker}</span>
              <span className="text-slate-500 font-mono text-sm">#{trade.id}</span>
            </div>
            <div className="text-xs font-sans mt-1" style={{ color }}>{sharkName}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-slate-500 text-xs font-sans mb-1">Shares</div>
            <div className="text-white font-mono">{trade.shares}</div>
          </div>
          <div>
            <div className="text-slate-500 text-xs font-sans mb-1">Price</div>
            <div className="text-white font-mono">${trade.price.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-slate-500 text-xs font-sans mb-2">Conviction</div>
            <ConvictionBar value={trade.conviction} color={color} />
          </div>
          <div>
            <div className="text-slate-500 text-xs font-sans mb-1">P&L</div>
            <div className={`font-mono ${trade.pnl == null ? 'text-slate-500' : pnlPos ? 'text-gain' : 'text-loss'}`}>
              {trade.pnl == null ? '—' : `${pnlPos ? '+' : ''}$${Math.abs(trade.pnl).toFixed(2)}`}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-xs font-sans mb-1">Entry</div>
            <div className="text-slate-400 text-xs font-mono">{fmtDate(trade.timestamp)}</div>
          </div>
          {trade.exit_time && (
            <div>
              <div className="text-slate-500 text-xs font-sans mb-1">Exit</div>
              <div className="text-slate-400 text-xs font-mono">{fmtDate(trade.exit_time)}</div>
            </div>
          )}
          <div>
            <div className="text-slate-500 text-xs font-sans mb-1">Stop Loss</div>
            <div className="text-slate-400 font-mono">
              {trade.stop_loss != null ? `$${trade.stop_loss.toFixed(2)}` : '—'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-xs font-sans mb-1">Target</div>
            <div className="text-slate-400 font-mono">
              {trade.target_price != null ? `$${trade.target_price.toFixed(2)}` : '—'}
            </div>
          </div>
        </div>

        <div className="border-t border-reef-border pt-4">
          <div className="text-slate-500 text-xs font-sans">
            Surfaced by <span style={{ color }}>{sharkName}</span>
            {trade.vetted_by && <> · Vetted by <span className="text-slate-400">{trade.vetted_by}</span></>}
          </div>
        </div>

        {(trade.apex_rationale ?? trade.reason) && (
          <div>
            <div className="text-slate-500 text-xs font-sans uppercase tracking-widest mb-2">
              Apex Rationale
            </div>
            <div className="card-elevated p-4 text-slate-200 text-xs font-sans leading-relaxed whitespace-pre-wrap">
              {trade.apex_rationale ?? trade.reason}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function TradesPage() {
  const { id } = useParams<{ id?: string }>()
  const [data, setData]   = useState<TradesResponse | null>(null)
  const [skip, setSkip]   = useState(0)
  const limit = 50

  useEffect(() => {
    if (!id) {
      fetchTrades(limit, skip).then(setData)
    }
  }, [id, skip])

  if (id) return <TradeDetail id={parseInt(id, 10)} />

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-slate-200 text-sm font-sans font-medium uppercase tracking-widest">
          Trade History
          {data && <span className="ml-2 text-slate-500 font-mono font-normal">({data.total})</span>}
        </h1>
      </div>

      {data ? (
        <>
          <TradesTable trades={data.trades} />
          {data.total > limit && (
            <div className="flex justify-center gap-3">
              <button
                disabled={skip === 0}
                onClick={() => setSkip(Math.max(0, skip - limit))}
                className="px-4 py-1.5 text-xs font-sans bg-reef-elevated hover:bg-reef-border rounded disabled:opacity-40 transition-colors"
              >
                Prev
              </button>
              <span className="text-slate-500 text-xs font-mono self-center">
                {skip + 1}–{Math.min(skip + limit, data.total)} of {data.total}
              </span>
              <button
                disabled={skip + limit >= data.total}
                onClick={() => setSkip(skip + limit)}
                className="px-4 py-1.5 text-xs font-sans bg-reef-elevated hover:bg-reef-border rounded disabled:opacity-40 transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="text-slate-500 text-sm animate-pulse">Loading...</div>
      )}
    </div>
  )
}
