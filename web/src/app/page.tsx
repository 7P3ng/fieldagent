'use client'
import { useState } from 'react'
import data from '@/lib/data.json'
import type { DemoData } from '@/lib/types'
import { ContractViewer } from '@/components/ContractViewer'
import { FindingsPanel } from '@/components/FindingsPanel'
import { ResultsPanel } from '@/components/ResultsPanel'

const demo = data as unknown as DemoData

export default function Home() {
  const [ci, setCi] = useState(0)
  const [active, setActive] = useState<number | null>(null)
  const contract = demo.contracts[ci]
  const r = demo.results

  return (
    <main className="max-w-[1180px] mx-auto px-6 py-10">
      {/* Hero */}
      <header className="mb-10">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-accent)' }} />
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-tertiary">
            Contract Red-Flag Finder · CUAD-graded
          </span>
        </div>
        <h1 className="text-[34px] font-semibold tracking-tight leading-none mb-3">
          FieldAgent
        </h1>
        <p className="text-secondary text-[15px] max-w-2xl leading-relaxed">
          An agent reads a real commercial contract and flags risk-bearing clauses — the exact span,
          a severity, and a plain-English “why this is risky” — graded span-IoU against{' '}
          <a href="https://www.atticusprojectai.org/cuad" className="accent underline decoration-dotted"
             target="_blank" rel="noreferrer">CUAD</a> gold, with a measured agentic lift over single-shot.
        </p>

        <div className="flex flex-wrap gap-4 mt-6">
          <Stat label="Detection F1" value={r.arms.pipeline_full.f1.toFixed(3)}
                sub={`P ${(r.arms.pipeline_full.precision * 100).toFixed(0)} / R ${(r.arms.pipeline_full.recall * 100).toFixed(0)} · ${r.contracts_processed} held-out contracts`}
                color="var(--color-accent)" />
          <Stat label="Lift vs keyword floor" value={`+${(r.arms.pipeline_full.f1 - r.arms.keyword.f1).toFixed(3)}`}
                sub={`F1 over a regex floor (0.337→${r.arms.pipeline_full.f1.toFixed(3)}) · single-shot LLM lower but output-budget-limited`}
                color="var(--color-low)" />
          <Stat label="Risk clause types" value={String(r.n_clause_types)}
                sub={`${r.total_gold_spans} gold spans · IoU ≥ ${r.iou_threshold}`}
                color="var(--color-text-primary)" />
        </div>
      </header>

      {/* Pipeline strip */}
      <div className="surface-2 border border-subtle rounded-lg px-5 py-3 mb-8 flex items-center gap-2 flex-wrap font-mono text-[11px] text-secondary">
        {['chunk', 'focused extraction', 'skeptic verification', 'dedupe / merge', 'structured findings'].map((s, i, a) => (
          <span key={s} className="flex items-center gap-2">
            <span>{s}</span>
            {i < a.length - 1 && <span className="text-tertiary">→</span>}
          </span>
        ))}
        <span className="ml-auto text-tertiary">model: {r.model}</span>
      </div>

      {/* Cross-model finding callout */}
      {demo.cross_model && (
        <div className="surface-1 border rounded-lg p-4 mb-8" style={{ borderColor: 'var(--color-medium-line)' }}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                  style={{ color: 'var(--color-medium)', background: 'var(--color-medium-bg)' }}>
              cross-model finding
            </span>
            <span className="text-[13px] font-medium">the agentic lift is model-specific</span>
          </div>
          <p className="text-[12.5px] text-secondary leading-relaxed">
            On DeepSeek, chunked extraction beats single-shot by <span className="font-mono">+0.45 F1</span> —
            but that gap is an artifact of DeepSeek&apos;s single-shot response <em>truncating</em> under
            reasoning-token pressure (17/20). On <strong>Claude Sonnet</strong> ({demo.cross_model.n_contracts}-contract
            subset), which finishes its one-pass response, single-shot
            (<span className="font-mono accent">F1 {demo.cross_model.single_shot.f1.toFixed(3)}</span>) <strong>ties</strong> the
            chunked pipeline (<span className="font-mono">{demo.cross_model.pipeline_chunked_no_verifier.f1.toFixed(3)}</span>) —
            chunking lift <span className="font-mono" style={{ color: 'var(--color-medium)' }}>{demo.cross_model.chunking_lift_f1.toFixed(3)}</span>.
            Cross-model validation caught what a single-model eval would have shipped as a headline.
          </p>
        </div>
      )}

      {/* Contract selector */}
      <div className="flex gap-1.5 mb-4 flex-wrap">
        {demo.contracts.map((c, i) => (
          <button
            key={c.doc_id}
            onClick={() => { setCi(i); setActive(null) }}
            className="font-mono text-[11px] px-2.5 py-1.5 rounded border transition-colors"
            style={{
              borderColor: i === ci ? 'var(--color-accent)' : 'var(--color-border)',
              background: i === ci ? 'var(--color-accent-dim)' : 'transparent',
              color: i === ci ? 'var(--color-accent)' : 'var(--color-text-secondary)',
            }}
          >
            {c.agreement_type}
          </button>
        ))}
      </div>
      <p className="text-tertiary text-[11px] mb-3 font-mono">
        {contract.title} · party names & dollar figures redacted (█) · CUAD excerpt, CC BY 4.0
      </p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mb-4 text-[11px] text-secondary">
        <span className="flex items-center gap-1.5"><span className="hl hl-high px-2">&nbsp;</span> high</span>
        <span className="flex items-center gap-1.5"><span className="hl hl-medium px-2">&nbsp;</span> medium</span>
        <span className="flex items-center gap-1.5"><span className="hl hl-low px-2">&nbsp;</span> low</span>
        <span className="flex items-center gap-1.5"><span className="hl hl-missed px-2">&nbsp;</span> missed gold (false negative)</span>
        <span className="ml-auto font-mono text-tertiary">
          recall this contract: {contract.gold_spans.filter((g) => g.matched).length}/{contract.gold_spans.length} gold clauses found
        </span>
      </div>

      {/* Document + findings */}
      <section className="grid lg:grid-cols-[1.4fr_1fr] gap-5 mb-10">
        <ContractViewer contract={contract} activeIndex={active} onSelect={setActive} />
        <FindingsPanel contract={contract} activeIndex={active} onSelect={setActive} />
      </section>

      {/* Results */}
      <h2 className="text-lg font-semibold tracking-tight mb-1">Measured results</h2>
      <p className="text-secondary text-[13px] mb-5">
        Span-IoU grading against CUAD gold (no LLM judge in the success path). Reproduce offline,
        zero cost: <code className="accent">make eval-dry</code>.
      </p>
      <ResultsPanel r={r} />

      <footer className="mt-12 pt-6 border-t border-subtle text-[12px] text-tertiary flex flex-wrap gap-x-6 gap-y-2">
        <span>FieldAgent · portfolio artifact</span>
        <a href="https://github.com/7P3ng/fieldagent" className="hover:text-secondary">source on GitHub</a>
        <span>Dataset: CUAD v1 — The Atticus Project (CC BY 4.0)</span>
        <span className="ml-auto">static demo · no live backend</span>
      </footer>
    </main>
  )
}

function Stat({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="surface-1 border border-subtle rounded-lg px-5 py-4 min-w-[200px] flex-1">
      <div className="text-[11px] uppercase tracking-wider text-tertiary mb-1">{label}</div>
      <div className="font-mono text-3xl leading-none mb-1.5" style={{ color }}>{value}</div>
      <div className="text-[11px] text-tertiary leading-snug">{sub}</div>
    </div>
  )
}
