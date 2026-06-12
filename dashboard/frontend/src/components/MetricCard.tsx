import { LineChart, Line } from 'recharts'

interface Props {
  label: string
  value: string
  sub?: string
  positive?: boolean
  negative?: boolean
  neutral?: boolean
  sparkline?: number[]
  trend?: 'up' | 'down' | 'flat'
}

export default function MetricCard({ label, value, sub, positive, negative, sparkline, trend }: Props) {
  const valueColor = positive ? 'text-gain' : negative ? 'text-loss' : 'text-white'
  const sparkColor = trend === 'up' ? 'var(--reef-gain)' : trend === 'down' ? 'var(--reef-loss)' : 'var(--reef-border)'
  const sparkData  = sparkline?.map((v) => ({ v }))

  return (
    <div className="card px-5 py-4 flex items-end justify-between">
      <div className="min-w-0">
        <div className="text-slate-500 text-xs font-sans uppercase tracking-widest mb-1">{label}</div>
        <div className={`text-2xl font-bold font-mono ${valueColor}`}>{value}</div>
        {sub && <div className="text-slate-500 text-xs font-sans mt-0.5">{sub}</div>}
      </div>
      {sparkData && sparkData.length > 1 && (
        <div className="shrink-0 ml-3 mb-0.5">
          <LineChart width={80} height={32} data={sparkData}>
            <Line
              type="monotone"
              dataKey="v"
              stroke={sparkColor}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </div>
      )}
    </div>
  )
}
