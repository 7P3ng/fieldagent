import type { Severity } from '@/lib/types'

const LABEL: Record<Severity, string> = { high: 'HIGH', medium: 'MEDIUM', low: 'LOW' }

export function SeverityBadge({ severity }: { severity: Severity }) {
  const color = `var(--color-${severity})`
  const bg = `var(--color-${severity}-bg)`
  return (
    <span
      className="font-mono text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded"
      style={{ color, background: bg }}
    >
      {LABEL[severity]}
    </span>
  )
}
