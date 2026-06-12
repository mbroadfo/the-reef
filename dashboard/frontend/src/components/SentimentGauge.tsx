interface Props {
  score: number
  label?: string
}

export default function SentimentGauge({ score, label }: Props) {
  const cx = 60, cy = 65, r = 50

  const bgStart = `${cx - r} ${cy}`
  const bgEnd   = `${cx + r} ${cy}`

  // Arc endpoint for score: angle sweeps from 180° (left) to 0° (right) through the top
  const angleRad = (180 - (score / 100) * 180) * (Math.PI / 180)
  const fx = (cx + r * Math.cos(angleRad)).toFixed(2)
  const fy = (cy - r * Math.sin(angleRad)).toFixed(2)

  const derivedLabel = score >= 60 ? 'Bullish' : score <= 40 ? 'Bearish' : 'Neutral'
  const displayLabel = label ?? derivedLabel
  const labelColor =
    displayLabel === 'Bullish' ? 'var(--reef-gain)'
    : displayLabel === 'Bearish' ? 'var(--reef-loss)'
    : '#94a3b8'

  return (
    <div className="flex flex-col items-center">
      <div className="text-xs text-slate-500 uppercase tracking-widest font-sans mb-1">
        AI Sentiment
      </div>
      <svg width="120" height="80" viewBox="0 0 120 80">
        {/* Background arc */}
        <path
          d={`M ${bgStart} A ${r} ${r} 0 0 1 ${bgEnd}`}
          fill="none"
          stroke="var(--reef-border)"
          strokeWidth="8"
          strokeLinecap="round"
        />
        {/* Score arc */}
        {score > 0 && (
          <path
            d={`M ${bgStart} A ${r} ${r} 0 0 1 ${fx} ${fy}`}
            fill="none"
            stroke={labelColor}
            strokeWidth="8"
            strokeLinecap="round"
          />
        )}
        {/* Score number */}
        <text
          x="60" y="58"
          textAnchor="middle"
          dominantBaseline="middle"
          fill="white"
          fontSize="22"
          fontFamily="'JetBrains Mono', monospace"
          fontWeight="600"
        >
          {score}
        </text>
        {/* Label */}
        <text
          x="60" y="74"
          textAnchor="middle"
          dominantBaseline="middle"
          fill={labelColor}
          fontSize="9"
          fontFamily="'Space Grotesk', sans-serif"
          letterSpacing="1.5"
          fontWeight="500"
        >
          {displayLabel.toUpperCase()}
        </text>
      </svg>
    </div>
  )
}
