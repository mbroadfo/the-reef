import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchTrades, fetchTradeDetail } from '../api'
import type { Trade, TradesResponse } from '../types'
import TradesTable from '../components/TradesTable'

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

  if (!trade) return <div className="text-zinc-600 text-sm animate-pulse">Loading...</div>

  const isBuy = trade.action === 'BUY'
  const pnlPos = (trade.pnl ?? 0) >= 0

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
      <button
        onClick={() => navigate('/trades')}
        className="text-zinc-500 hover:text-zinc-300 text-xs transition-colors"
      >
        ← Back to Trades
      </button>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <div className="flex items-center gap-4">
          <span className={`text-2xl font-bold ${isBuy ? 'text-blue-400' : 'text-amber-400'}`}>
            {trade.action}
          </span>
          <span className="text-2xl font-bold text-zinc-100">{trade.ticker}</span>
          <span className="text-zinc-500">#{trade.id}</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-zinc-600 text-xs mb-1">Shares</div>
            <div className="text-zinc-100">{trade.shares}</div>
          </div>
          <div>
            <div className="text-zinc-600 text-xs mb-1">Price</div>
            <div className="text-zinc-100">${trade.price.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-zinc-600 text-xs mb-1">Conviction</div>
            <div className="text-zinc-100">{trade.conviction}/10</div>
          </div>
          <div>
            <div className="text-zinc-600 text-xs mb-1">P&L</div>
            <div className={trade.pnl == null ? 'text-zinc-500' : pnlPos ? 'text-emerald-400' : 'text-red-400'}>
              {trade.pnl == null ? '—' : `${pnlPos ? '+' : ''}$${Math.abs(trade.pnl).toFixed(2)}`}
            </div>
          </div>
          <div>
            <div className="text-zinc-600 text-xs mb-1">Entry</div>
            <div className="text-zinc-400 text-xs">{fmtDate(trade.timestamp)}</div>
          </div>
          {trade.exit_time && (
            <div>
              <div className="text-zinc-600 text-xs mb-1">Exit</div>
              <div className="text-zinc-400 text-xs">{fmtDate(trade.exit_time)}</div>
            </div>
          )}
          <div>
            <div className="text-zinc-600 text-xs mb-1">Stop Loss</div>
            <div className="text-zinc-400">{trade.stop_loss != null ? `$${trade.stop_loss.toFixed(2)}` : '—'}</div>
          </div>
          <div>
            <div className="text-zinc-600 text-xs mb-1">Target</div>
            <div className="text-zinc-400">{trade.target_price != null ? `$${trade.target_price.toFixed(2)}` : '—'}</div>
          </div>
        </div>

        <div className="border-t border-zinc-800 pt-4">
          <div className="text-zinc-500 text-xs mb-1">Surfaced by {trade.surfaced_by} · Vetted by {trade.vetted_by}</div>
        </div>

        {trade.reason && (
          <div>
            <div className="text-zinc-500 text-xs uppercase tracking-wider mb-2">Apex Rationale</div>
            <div className="bg-zinc-950 border border-zinc-800 rounded p-4 text-zinc-300 text-xs leading-relaxed whitespace-pre-wrap">
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
  const [data, setData] = useState<TradesResponse | null>(null)
  const [skip, setSkip] = useState(0)
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
        <h1 className="text-zinc-300 text-sm font-medium uppercase tracking-wider">
          Trade History
          {data && <span className="ml-2 text-zinc-600 font-normal">({data.total})</span>}
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
                className="px-4 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded disabled:opacity-40 transition-colors"
              >
                Prev
              </button>
              <span className="text-zinc-600 text-xs self-center">
                {skip + 1}–{Math.min(skip + limit, data.total)} of {data.total}
              </span>
              <button
                disabled={skip + limit >= data.total}
                onClick={() => setSkip(skip + limit)}
                className="px-4 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded disabled:opacity-40 transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="text-zinc-600 text-sm animate-pulse">Loading...</div>
      )}
    </div>
  )
}
