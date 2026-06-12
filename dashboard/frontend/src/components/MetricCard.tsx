interface Props {
  label: string
  value: string
  sub?: string
  positive?: boolean
  negative?: boolean
  neutral?: boolean
}

export default function MetricCard({ label, value, sub, positive, negative }: Props) {
  const valueColor = positive ? 'text-gain' : negative ? 'text-loss' : 'text-white'

  return (
    <div className="card px-5 py-4">
      <div className="text-slate-500 text-xs font-sans uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${valueColor}`}>{value}</div>
      {sub && <div className="text-slate-500 text-xs font-sans mt-0.5">{sub}</div>}
    </div>
  )
}
