export const SHARK_COLORS: Record<string, string> = {
  'Hunter Shark':     'var(--shark-momentum)',
  'Research Shark':   'var(--shark-news)',
  'Macro Shark':      'var(--shark-macro)',
  'Sentiment Shark':  'var(--shark-sentiment)',
  'Contrarian Shark': 'var(--shark-contrarian)',
  'Risk Shark':       'var(--shark-options)',
  'Wildcard Shark':   'var(--shark-value)',
  'Apex Shark':       'var(--shark-apex)',
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
  'Hunter Shark':     'hue-rotate(70deg)  saturate(2.5) brightness(1.15)',
  'Research Shark':   'hue-rotate(0deg)   saturate(1.8) brightness(1.05)',
  'Macro Shark':      'hue-rotate(335deg) saturate(2.0) brightness(1.05)',
  'Sentiment Shark':  'hue-rotate(205deg) saturate(2.5) brightness(1.20)',
  'Contrarian Shark': 'hue-rotate(335deg) saturate(1.6) brightness(1.05)',
  'Risk Shark':       'hue-rotate(180deg) saturate(2.5) brightness(1.15)',
  'Wildcard Shark':   'hue-rotate(110deg) saturate(2.0) brightness(1.10)',
  'Apex Shark':       'hue-rotate(0deg)   saturate(0.15) brightness(0.90)',
}

export function getSharkFilter(name: string): string {
  const normalized = normalizeSharkName(name)
  return SHARK_FILTERS[normalized] ?? 'saturate(0.4) brightness(0.8)'
}

export const AQUARIUM_ROSTER = [
  'Hunter Shark',
  'Research Shark',
  'Macro Shark',
  'Sentiment Shark',
  'Contrarian Shark',
  'Risk Shark',
  'Wildcard Shark',
]
