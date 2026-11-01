import { useId } from 'react'

// Original flat SVG sharks, drawn for this project. Each species is chosen to fit the pod's actual strategy:
//   mako        - Momentum: built for speed, charges at breakouts that are already running
//   hammerhead  - Contrarian: eyes set wide apart, looking where the crowd is not (buys what has been sold)
//   greatwhite  - Apex: the large, calm top predator who decides, and does not hunt
export type Species = 'mako' | 'hammerhead' | 'greatwhite'

interface Palette { top: string; belly: string; fin: string; accent: string }

const PALETTE: Record<Species, Palette> = {
  mako:       { top: '#7c3aed', belly: '#ddd6fe', fin: '#5b21b6', accent: '#c4b5fd' },
  hammerhead: { top: '#b7791f', belly: '#fef3c7', fin: '#8a5a12', accent: '#fcd34d' },
  greatwhite: { top: '#7b8ba3', belly: '#f8fafc', fin: '#5f6f87', accent: '#f5c451' },
}

export default function SharkArt({ species, size = 200, className = '', sleeping = false, charging = false, glow = false }:
  { species: Species; size?: number; className?: string; sleeping?: boolean; charging?: boolean; glow?: boolean }) {
  const id = useId().replace(/:/g, '')
  const c = sleeping ? { top: '#475569', belly: '#94a3b8', fin: '#334155', accent: '#94a3b8' } : PALETTE[species]
  const w = size, h = size * 0.5
  return (
    <svg viewBox="0 0 260 130" width={w} height={h} className={className} role="img" aria-label={`${species} shark`} style={{ overflow: 'visible', filter: glow ? 'drop-shadow(0 0 14px rgba(245,196,81,0.4))' : undefined }}>
      <defs>
        <linearGradient id={`b${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={c.top} /><stop offset="0.56" stopColor={c.top} />
          <stop offset="0.57" stopColor={c.belly} /><stop offset="1" stopColor={c.belly} />
        </linearGradient>
        <clipPath id={`k${id}`}>
          {species === 'hammerhead'
            ? <path d="M30 66 C60 50 118 44 176 52 C196 55 204 60 206 65 C204 72 196 77 176 80 C118 88 60 82 30 68 Z" />
            : species === 'mako'
              ? <path d="M246 66 C216 50 166 40 112 44 C80 46 52 56 30 65 C52 74 80 82 112 84 C166 86 216 82 246 66 Z" />
              : <path d="M240 68 C214 44 160 36 108 42 C78 46 52 58 30 66 C52 76 80 86 112 88 C164 90 214 86 240 68 Z" />}
        </clipPath>
      </defs>

      {charging && species === 'mako' && (
        <g stroke={c.accent} strokeWidth="2.2" strokeLinecap="round" opacity="0.55">
          <path d="M-8 44h38" /><path d="M-18 66h42" /><path d="M-8 88h36" />
        </g>
      )}

      <g className={species === 'mako' ? 'fish-fast' : species === 'hammerhead' ? 'fish-slow' : 'fish-calm'}>
        {/* tail */}
        <g className={species === 'mako' ? 'tail-fast' : species === 'hammerhead' ? 'tail-slow' : 'tail-calm'} style={{ transformBox: 'fill-box', transformOrigin: '90% 50%' }}>
          {species === 'mako'
            ? <path d="M36 65 L2 20 C14 40 22 54 26 65 C22 78 14 92 8 112 Z" fill={c.fin} />
            : species === 'hammerhead'
              ? <path d="M34 66 L4 22 C16 40 24 54 28 66 C24 80 20 92 12 104 Z" fill={c.fin} />
              : <path d="M36 66 L6 24 C16 42 24 56 28 66 C24 80 18 92 10 110 Z" fill={c.fin} />}
        </g>

        {/* pectoral and dorsal fins sit behind the body edge */}
        {species === 'mako' && <>
          <path d="M120 44 C128 22 140 10 150 8 C146 24 148 36 154 46 Z" fill={c.fin} />
          <path d="M172 72 C160 94 142 104 124 108 C140 94 148 82 152 72 Z" fill={c.fin} />
          <path d="M60 78 C54 86 48 90 42 92 C48 84 50 80 52 76 Z" fill={c.fin} />
        </>}
        {species === 'hammerhead' && <>
          <path d="M104 50 C112 22 130 6 148 4 C142 22 146 40 154 53 Z" fill={c.fin} />
          <path d="M156 78 C146 100 128 112 108 114 C126 100 134 88 138 78 Z" fill={c.fin} />
          <path d="M66 80 C60 90 54 94 46 96 C52 88 54 84 56 80 Z" fill={c.fin} />
        </>}
        {species === 'greatwhite' && <>
          <path d="M110 42 C118 14 134 -4 152 -8 C146 12 150 32 160 46 Z" fill={c.fin} />
          <path d="M166 80 C154 104 134 118 112 120 C130 104 138 92 142 82 Z" fill={c.fin} />
          <path d="M64 82 C58 92 52 98 44 100 C50 92 52 86 54 82 Z" fill={c.fin} />
        </>}

        {/* body, countershaded */}
        <g clipPath={`url(#k${id})`}>
          <rect x="0" y="0" width="260" height="130" fill={`url(#b${id})`} />
        </g>
        {species === 'hammerhead' && (
          <>
            {/* the cephalofoil: a wide, flat head with an eye at each end */}
            <rect x="196" y="38" width="30" height="56" rx="13" fill={c.top} />
            <rect x="196" y="38" width="30" height="56" rx="13" fill="none" stroke={c.belly} strokeOpacity="0.35" />
            <circle cx="216" cy="43" r="4.6" fill="#0b1220" /><circle cx="217.2" cy="41.8" r="1.4" fill="#fff" />
            <circle cx="216" cy="89" r="4.6" fill="#0b1220" /><circle cx="217.2" cy="87.8" r="1.4" fill="#fff" />
          </>
        )}
        {species !== 'hammerhead' && (
          <>
            <circle cx={species === 'mako' ? 206 : 204} cy={species === 'mako' ? 60 : 60} r={species === 'greatwhite' ? 4.4 : 3.6} fill="#0b1220" />
            <circle cx={species === 'mako' ? 207 : 205} cy={59} r="1.2" fill="#fff" />
          </>
        )}
        {/* gill slits and mouth line */}
        <g stroke={sleeping ? '#1e293b' : '#0b1220'} strokeOpacity="0.55" strokeWidth="1.8" strokeLinecap="round" fill="none">
          <path d={species === 'hammerhead' ? 'M168 56 q-3 9 0 18' : 'M178 52 q-4 11 0 22'} />
          <path d={species === 'hammerhead' ? 'M160 56 q-3 9 0 18' : 'M170 51 q-4 11 0 22'} />
          <path d={species === 'hammerhead' ? 'M152 55 q-3 9 0 18' : 'M162 50 q-4 11 0 22'} />
          {species === 'greatwhite' && <path d="M236 70 q-12 6 -26 3" strokeOpacity="0.5" />}
          {species === 'mako' && <path d="M240 68 q-10 5 -22 2" strokeOpacity="0.5" />}
        </g>
        {species === 'greatwhite' && (
          <g fill="#f8fafc" opacity="0.85"><path d="M222 74 l2 5 l2 -5 z" /><path d="M214 75 l2 5 l2 -5 z" /><path d="M206 75 l2 5 l2 -5 z" /></g>
        )}
      </g>
    </svg>
  )
}

// Per-pod art for the shared pod pages; inactive pods keep the grayscale illustration used before.
export const SPECIES: Record<string, Species | undefined> = { momentum: 'mako', contrarian: 'hammerhead' }
