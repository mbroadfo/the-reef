import type { ReactNode } from 'react'
import { LineChart, Line } from 'recharts'

const FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

interface StatPillProps {
  label: string
  value: string
  change?: string
  positive?: boolean
  sparkline?: number[]
  children?: ReactNode
}

export default function StatPill({ label, value, change, positive, sparkline, children }: StatPillProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      padding: '0 20px',
      borderRight: '1px solid var(--reef-border)',
      minWidth: '130px',
      height: '100%',
    }}>
      <div style={{
        fontSize: '10px',
        fontFamily: FONT_SANS,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: '#64748b',
        marginBottom: '3px',
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{
          fontSize: '17px',
          fontWeight: '700',
          fontFamily: FONT_MONO,
          color: '#f1f5f9',
          lineHeight: 1,
        }}>
          {value}
        </span>
        {sparkline && sparkline.length > 1 && (
          <LineChart width={56} height={22} data={sparkline.map(v => ({ v }))}>
            <Line
              type="monotone"
              dataKey="v"
              stroke={positive ? 'var(--reef-gain)' : 'var(--reef-loss)'}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        )}
        {children}
      </div>
      {change && (
        <div style={{
          fontSize: '11px',
          fontFamily: FONT_MONO,
          color: positive ? 'var(--reef-gain)' : 'var(--reef-loss)',
          marginTop: '2px',
        }}>
          {change}
        </div>
      )}
    </div>
  )
}
