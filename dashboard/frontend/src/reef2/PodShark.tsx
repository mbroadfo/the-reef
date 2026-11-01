import sharkImg from '../assets/shark-base.png'
import SharkArt, { SPECIES } from './Sharks'
import type { Pod } from './types'

// Hue shifts applied to the single shark illustration so each pod is recognisable at a glance.
const FILTER: Record<string, string> = {
  momentum:   'hue-rotate(240deg) saturate(1.5)',
  contrarian: 'hue-rotate(40deg) saturate(1.8) brightness(1.1)',
  value:      'hue-rotate(120deg) saturate(1.3)',
  macro:      'hue-rotate(170deg) saturate(1.4)',
  earnings:   'hue-rotate(20deg) saturate(1.8)',
  news:       'hue-rotate(200deg) saturate(1.3)',
}

export const POD_HEX: Record<string, string> = {
  momentum: '#a855f7', contrarian: '#eab308', value: '#22c55e', macro: '#06b6d4', earnings: '#f97316', news: '#3b82f6',
}

export default function PodShark({ pod, size = 72 }: { pod: Pod; size?: number }) {
  const active = pod.status === 'ACTIVE'
  const species = SPECIES[pod.pod_id]
  if (active && species) return <div style={{ width: size * 1.6, height: size * 0.8, flexShrink: 0 }}><SharkArt species={species} size={size * 1.6} /></div>
  return (
    <div className={active ? 'shark-bob' : ''} style={{ width: size, height: size, flexShrink: 0 }}>
      <img
        src={sharkImg}
        alt={`${pod.name} shark${active ? '' : ' (inactive)'}`}
        style={{
          width: '100%', height: '100%', objectFit: 'contain',
          filter: active ? `${FILTER[pod.pod_id] ?? 'none'} drop-shadow(0 0 8px ${POD_HEX[pod.pod_id]}66)` : 'grayscale(1) brightness(0.55)',
          opacity: active ? 1 : 0.55,
        }}
      />
    </div>
  )
}
