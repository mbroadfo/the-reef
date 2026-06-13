// Phase 3: reconcile these keys against actual surfaced_by values from MongoDB
// Current live agents write: "Momentum Hunter", "Earnings Hunter", "News Hunter",
// "Value Analyst", "Macro Analyst", "Contrarian Analyst", "Apex Shark"
export const SHARK_COLORS: Record<string, string> = {
  // Canonical display names (spec)
  'Momentum Shark':    'var(--shark-momentum)',
  'News Shark':        'var(--shark-news)',
  'Macro Shark':       'var(--shark-macro)',
  'Value Shark':       'var(--shark-value)',
  'Contrarian Shark':  'var(--shark-contrarian)',
  'Hunter Shark':      'var(--shark-momentum)',
  'Fundamental Shark': 'var(--shark-value)',
  'Earnings Shark':    'var(--shark-earnings)',
  // Actual surfaced_by values from MongoDB
  'Momentum Hunter':   'var(--shark-momentum)',
  'Earnings Hunter':   'var(--shark-earnings)',
  'News Hunter':       'var(--shark-news)',
  'Value Analyst':     'var(--shark-value)',
  'Macro Analyst':     'var(--shark-macro)',
  'Contrarian Analyst':'var(--shark-contrarian)',
  'Apex Shark':        'var(--shark-apex)',
}

export function normalizeSharkName(name: string): string {
  return name.replace(/ Shark Shark$/, ' Shark')
}

export function getSharkColor(name: string): string {
  return SHARK_COLORS[normalizeSharkName(name)] ?? 'var(--shark-apex)'
}

export function getSharkInitials(name: string): string {
  return normalizeSharkName(name)
    .split(/\s+/)
    .filter(Boolean)
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

export const SHARK_FILTERS: Record<string, string> = {
  'Momentum Shark':    'hue-rotate(70deg)  saturate(2.5) brightness(1.15)',
  'News Shark':        'hue-rotate(0deg)   saturate(1.8) brightness(1.05)',
  'Macro Shark':       'hue-rotate(335deg) saturate(2.0) brightness(1.05)',
  'Options Shark':     'hue-rotate(180deg) saturate(2.5) brightness(1.15)',
  'Value Shark':       'hue-rotate(270deg) saturate(2.0) brightness(1.10)',
  'Sentiment Shark':   'hue-rotate(205deg) saturate(2.5) brightness(1.20)',
  'Crypto Shark':      'hue-rotate(0deg)   saturate(0.15) brightness(0.90)',
  'Hunter Shark':      'hue-rotate(70deg)  saturate(2.0) brightness(1.10)',
  'Fundamental Shark': 'hue-rotate(270deg) saturate(1.6) brightness(1.05)',
  'Contrarian Shark':  'hue-rotate(335deg) saturate(1.6) brightness(1.05)',
  'Earnings Shark':    'hue-rotate(0deg)   saturate(1.8) brightness(1.05)',
}

export function getSharkFilter(name: string): string {
  const normalized = normalizeSharkName(name)
  return SHARK_FILTERS[normalized] ?? 'saturate(0.4) brightness(0.8)'
}

export const AQUARIUM_ROSTER = [
  'Momentum Shark',
  'News Shark',
  'Macro Shark',
  'Options Shark',
  'Value Shark',
  'Sentiment Shark',
  'Crypto Shark',
]
