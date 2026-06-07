interface Props {
  label: string
  value: string
  sub?: string
  positive?: boolean
  negative?: boolean
  neutral?: boolean
}

export default function MetricCard({ label, value, sub, positive, negative }: Props) {
  const valueColor = positive
    ? 'text-emerald-400'
    : negative
    ? 'text-red-400'
    : 'text-zinc-100'

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-5 py-4">
      <div className="text-zinc-500 text-xs uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${valueColor}`}>{value}</div>
      {sub && <div className="text-zinc-500 text-xs mt-0.5">{sub}</div>}
    </div>
  )
}
