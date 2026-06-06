'use client'
import type { ContractCase } from '@/lib/types'
import { SeverityBadge } from './SeverityBadge'

const SEV_RANK = { high: 0, medium: 1, low: 2 } as const

export function FindingsPanel({
  contract,
  activeIndex,
  onSelect,
}: {
  contract: ContractCase
  activeIndex: number | null
  onSelect: (i: number) => void
}) {
  const order = contract.findings
    .map((f, i) => ({ f, i }))
    .sort((a, b) => SEV_RANK[a.f.severity] - SEV_RANK[b.f.severity] || b.f.confidence - a.f.confidence)

  return (
    <div className="flex flex-col h-[640px]">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold tracking-tight">
          Findings <span className="text-tertiary font-normal">({contract.findings.length})</span>
        </h3>
        <span className="font-mono text-[11px] text-tertiary">severity-sorted</span>
      </div>
      <div className="flex flex-col gap-2 overflow-y-auto pr-1">
        {order.map(({ f, i }) => {
          const active = i === activeIndex
          return (
            <button
              key={i}
              onClick={() => onSelect(i)}
              className="text-left surface-1 border rounded-lg p-3 transition-colors"
              style={{
                borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                background: active ? 'var(--color-accent-dim)' : 'var(--color-surface-1)',
              }}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <SeverityBadge severity={f.severity} />
                <span className="text-[13px] font-medium">{f.clause_type}</span>
                <span className="ml-auto font-mono text-[10px] text-tertiary">
                  {(f.confidence * 100).toFixed(0)}%
                </span>
                <span
                  className="font-mono text-[10px] px-1 py-0.5 rounded"
                  style={{
                    color: f.matched_gold ? 'var(--color-ok)' : 'var(--color-text-tertiary)',
                    background: f.matched_gold ? 'rgba(74,222,128,0.10)' : 'transparent',
                    border: f.matched_gold ? 'none' : '1px solid var(--color-border)',
                  }}
                  title={f.matched_gold ? 'Matches CUAD gold span (IoU ≥ 0.5)' : 'No matching gold span (≈ false positive)'}
                >
                  {f.matched_gold ? '✓ gold' : 'unmatched'}
                </span>
              </div>
              <p className="text-[12px] text-secondary leading-snug mb-1.5">{f.risk_note}</p>
              <p className="font-mono text-[11px] text-tertiary leading-snug line-clamp-3 border-l-2 pl-2"
                 style={{ borderColor: `var(--color-${f.severity}-line)` }}>
                “{f.span_text.trim().slice(0, 220)}{f.span_text.length > 220 ? '…' : ''}”
              </p>
            </button>
          )
        })}
        {contract.findings.length === 0 && (
          <p className="text-[12px] text-tertiary">No risk-bearing clauses detected.</p>
        )}
      </div>
    </div>
  )
}
