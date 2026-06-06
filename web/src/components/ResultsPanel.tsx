import type { Results } from '@/lib/types'

function pct(x: number) {
  return (x * 100).toFixed(1)
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const w = max > 0 ? Math.max(2, (value / max) * 100) : 0
  return (
    <div className="h-2 rounded-full" style={{ width: '100%', background: 'var(--color-surface-3)' }}>
      <div className="h-2 rounded-full" style={{ width: `${w}%`, background: color }} />
    </div>
  )
}

export function ResultsPanel({ r }: { r: Results }) {
  const arms: { key: keyof Results['arms']; label: string; color: string }[] = [
    { key: 'keyword', label: 'Keyword / regex floor', color: 'var(--color-text-tertiary)' },
    { key: 'single_shot', label: 'Single-shot LLM (baseline)', color: 'var(--color-medium)' },
    { key: 'pipeline_no_verifier', label: 'Pipeline − verifier', color: 'var(--color-low)' },
    { key: 'pipeline_full', label: 'Pipeline (full, agentic)', color: 'var(--color-accent)' },
  ]
  const maxF1 = Math.max(...arms.map((a) => r.arms[a.key].f1))

  return (
    <section className="grid lg:grid-cols-2 gap-5">
      <div className="surface-1 border border-subtle rounded-lg p-5">
        <h3 className="text-sm font-semibold mb-4">Detection F1 by approach</h3>
        <div className="flex flex-col gap-3.5">
          {arms.map((a) => {
            const m = r.arms[a.key]
            return (
              <div key={a.key}>
                <div className="flex items-baseline justify-between mb-1 text-[12px]">
                  <span className="text-secondary">{a.label}</span>
                  <span className="font-mono">
                    <span style={{ color: a.color }}>{m.f1.toFixed(3)}</span>
                    <span className="text-tertiary"> · P {pct(m.precision)} / R {pct(m.recall)}</span>
                  </span>
                </div>
                <Bar value={m.f1} max={maxF1} color={a.color} />
                <div className="font-mono text-[10px] text-tertiary mt-0.5">
                  95% CI [{m.ci95[0].toFixed(3)}, {m.ci95[1].toFixed(3)}]
                </div>
              </div>
            )
          })}
        </div>
        <div className="mt-5 pt-4 border-t border-subtle grid grid-cols-2 gap-3 text-center">
          <div>
            <div className="font-mono text-2xl accent">+{(r.arms.pipeline_full.f1 - r.arms.keyword.f1).toFixed(3)}</div>
            <div className="text-[11px] text-tertiary mt-0.5">lift vs keyword floor (single-shot lower, budget-limited)</div>
          </div>
          <div>
            <div className="font-mono text-2xl" style={{ color: 'var(--color-low)' }}>
              {r.verifier_contribution_f1 >= 0 ? '+' : ''}{r.verifier_contribution_f1.toFixed(3)}
            </div>
            <div className="text-[11px] text-tertiary mt-0.5">verifier ΔF1 (precision {(r.arms.pipeline_no_verifier.precision*100).toFixed(0)}→{(r.arms.pipeline_full.precision*100).toFixed(0)})</div>
          </div>
        </div>
      </div>

      <div className="surface-1 border border-subtle rounded-lg p-5">
        <h3 className="text-sm font-semibold mb-4">Per-clause-type F1 (full pipeline)</h3>
        <div className="overflow-y-auto max-h-[300px]">
          <table className="w-full text-[12px]">
            <thead className="text-tertiary text-[10px] uppercase tracking-wider">
              <tr className="text-left">
                <th className="pb-2 font-medium">Clause type</th>
                <th className="pb-2 font-medium text-right">Gold</th>
                <th className="pb-2 font-medium text-right">P</th>
                <th className="pb-2 font-medium text-right">R</th>
                <th className="pb-2 font-medium text-right">F1</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {r.per_type.map((t) => (
                <tr key={t.clause_type} className="border-t border-subtle">
                  <td className="py-1.5 pr-2 font-sans text-secondary">{t.clause_type}</td>
                  <td className="py-1.5 text-right text-tertiary">{t.gold}</td>
                  <td className="py-1.5 text-right">{t.precision.toFixed(2)}</td>
                  <td className="py-1.5 text-right">{t.recall.toFixed(2)}</td>
                  <td className="py-1.5 text-right accent">{t.f1.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 pt-4 border-t border-subtle">
          <h4 className="text-[11px] uppercase tracking-wider text-tertiary mb-2">IoU-threshold sensitivity (F1)</h4>
          <div className="flex gap-4 font-mono text-[12px]">
            {Object.entries(r.iou_threshold_sweep).map(([thr, v]) => (
              <div key={thr} className="flex-1 text-center surface-2 rounded p-2">
                <div className="text-[10px] text-tertiary">IoU {thr}</div>
                <div className="accent">{v.pipeline_full.toFixed(2)}</div>
                <div className="text-tertiary text-[10px]">ss {v.single_shot.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
