/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Space Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      colors: {
        reef: {
          bg:       'var(--reef-bg)',
          card:     'var(--reef-card)',
          elevated: 'var(--reef-elevated)',
          border:   'var(--reef-border)',
          gain:     'var(--reef-gain)',
          loss:     'var(--reef-loss)',
        },
        shark: {
          // Live agents
          momentum:   'var(--shark-momentum)',
          earnings:   'var(--shark-earnings)',
          news:       'var(--shark-news)',
          value:      'var(--shark-value)',
          macro:      'var(--shark-macro)',
          contrarian: 'var(--shark-contrarian)',
          apex:       'var(--shark-apex)',
          // Future expansion
          options:    'var(--shark-options)',
          sentiment:  'var(--shark-sentiment)',
          crypto:     'var(--shark-crypto)',
        },
      },
      boxShadow: {
        'card-glow': '0 0 0 1px var(--reef-border), 0 0 16px 0 rgba(0,255,136,0.06)',
      },
    },
  },
  plugins: [],
}
