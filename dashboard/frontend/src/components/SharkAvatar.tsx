import { useState } from 'react'
import { getSharkColor, normalizeSharkName } from '../utils/sharks'
import sharkImg from '../assets/shark-base.png'

const TINT: Record<string, string> = {
  momentum:   'hue-rotate(240deg) saturate(1.4)',
  news:       'hue-rotate(200deg) saturate(1.2)',
  macro:      'hue-rotate(170deg) saturate(1.3)',
  options:    'hue-rotate(30deg) saturate(1.5)',
  value:      'hue-rotate(120deg) saturate(1.2)',
  sentiment:  'hue-rotate(50deg) saturate(1.4)',
}

function getTint(name: string): string {
  const lower = name.toLowerCase()
  for (const [key, filter] of Object.entries(TINT)) {
    if (lower.includes(key)) return filter
  }
  return 'none'
}

const SIZE: Record<string, string> = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-xs',
  lg: 'w-16 h-16 text-base',
}

interface Props {
  name: string
  size?: 'sm' | 'md' | 'lg'
}

export default function SharkAvatar({ name, size = 'md' }: Props) {
  const [imgFailed, setImgFailed] = useState(false)
  const normalized = normalizeSharkName(name)
  const color = getSharkColor(normalized)
  const initial = normalized.trim()[0]?.toUpperCase() ?? '?'
  const shadow = `0 0 10px 1px ${color}33`

  const base = (
    <div
      className={`${SIZE[size]} rounded-full flex items-center justify-center bg-reef-elevated border-2 font-bold font-sans shrink-0`}
      style={{ borderColor: color, color, boxShadow: shadow }}
    >
      {initial}
    </div>
  )

  if (imgFailed) return base

  return (
    <div
      className={`${SIZE[size]} rounded-full bg-reef-elevated border-2 overflow-hidden shrink-0`}
      style={{ borderColor: color, boxShadow: shadow }}
    >
      <img
        src={sharkImg}
        alt={normalized}
        onError={() => setImgFailed(true)}
        className="w-full h-full object-contain"
        style={{ filter: getTint(normalized) }}
      />
    </div>
  )
}
