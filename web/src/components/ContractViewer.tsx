'use client'
import { useMemo, useRef, useEffect } from 'react'
import type { ContractCase, Severity } from '@/lib/types'

interface Segment {
  text: string
  severity?: Severity
  findingIndex?: number
}

// Build non-overlapping display segments from the contract text + finding spans.
function segment(c: ContractCase): Segment[] {
  const marks = c.findings
    .map((f, i) => ({ start: f.start, end: f.end, severity: f.severity, i }))
    .filter((m) => m.start >= 0 && m.end > m.start)
    .sort((a, b) => a.start - b.start)
  const segs: Segment[] = []
  let pos = 0
  for (const m of marks) {
    if (m.start < pos) continue // skip overlaps (already covered)
    if (m.start > pos) segs.push({ text: c.text.slice(pos, m.start) })
    segs.push({ text: c.text.slice(m.start, m.end), severity: m.severity, findingIndex: m.i })
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
          if (s.severity === undefined) return <span key={idx}>{s.text}</span>
          const active = s.findingIndex === activeIndex
          return (
            <span
              key={idx}
              ref={active ? activeRef : null}
              className={`hl hl-${s.severity}${active ? ' hl-active' : ''}`}
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
