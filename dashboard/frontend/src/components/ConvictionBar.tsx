interface Props {
  value: number
  max?: number
  color?: string
}

export default function ConvictionBar({ value, max = 10, color }: Props) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="w-full h-1.5 rounded-full bg-reef-border overflow-hidden">
      <div
        className="h-full rounded-full transition-[width] duration-300 ease-out"
        style={{ width: `${pct}%`, background: color ?? 'var(--reef-gain)' }}
      />
    </div>
  )
}
