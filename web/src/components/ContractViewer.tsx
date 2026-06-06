'use client'
import { useMemo, useRef, useEffect } from 'react'
import type { ContractCase, Severity } from '@/lib/types'

type Kind = Severity | 'missed'

interface Mark {
  start: number
  end: number
  kind: Kind
  findingIndex?: number
}

interface Segment {
  text: string
  kind?: Kind
  findingIndex?: number
}

// Build non-overlapping display segments: detected findings (by severity) take
// priority; gold clauses we MISSED (unmatched gold) are shown dashed so the demo
// visualizes recall, not just precision.
function segment(c: ContractCase): Segment[] {
  const marks: Mark[] = [
    ...c.findings
      .map((f, i) => ({ start: f.start, end: f.end, kind: f.severity as Kind, findingIndex: i }))
      .filter((m) => m.start >= 0 && m.end > m.start),
    ...c.gold_spans
      .filter((g) => !g.matched)
      .map((g) => ({ start: g.start, end: g.end, kind: 'missed' as Kind })),
  ].sort((a, b) => a.start - b.start || (a.kind === 'missed' ? 1 : -1))

  const segs: Segment[] = []
  let pos = 0
  for (const m of marks) {
    if (m.start < pos) continue // overlap already covered (findings win)
    if (m.start > pos) segs.push({ text: c.text.slice(pos, m.start) })
    segs.push({ text: c.text.slice(m.start, m.end), kind: m.kind, findingIndex: m.findingIndex })
    pos = m.end
  }
  if (pos < c.text.length) segs.push({ text: c.text.slice(pos) })
  return segs
}

export function ContractViewer({
  contract,
  activeIndex,
  onSelect,
}: {
  contract: ContractCase
  activeIndex: number | null
  onSelect: (i: number) => void
}) {
  const segs = useMemo(() => segment(contract), [contract])
  const activeRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [activeIndex])

  return (
    <div className="surface-1 border border-subtle rounded-lg h-[640px] overflow-y-auto p-6">
      <pre className="whitespace-pre-wrap font-mono text-[12.5px] leading-relaxed text-secondary">
        {segs.map((s, idx) => {
          if (s.kind === undefined) return <span key={idx}>{s.text}</span>
          if (s.kind === 'missed') {
            return (
              <span key={idx} className="hl hl-missed" title="Gold clause the agent missed (false negative)">
                {s.text}
              </span>
            )
          }
          const active = s.findingIndex === activeIndex
          return (
            <span
              key={idx}
              ref={active ? activeRef : null}
              className={`hl hl-${s.kind}${active ? ' hl-active' : ''}`}
              onClick={() => onSelect(s.findingIndex!)}
              style={{ color: 'var(--color-text-primary)' }}
            >
              {s.text}
            </span>
          )
        })}
      </pre>
    </div>
  )
}
