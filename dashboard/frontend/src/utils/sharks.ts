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
