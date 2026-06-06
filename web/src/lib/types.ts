export type Severity = 'high' | 'medium' | 'low'

export interface Finding {
  clause_type: string
  span_text: string
  start: number
  end: number
  severity: Severity
  risk_note: string
  confidence: number
  rationale: string
  matched_gold: boolean
}

export interface GoldSpanLite {
  clause_type: string
  start: number
  end: number
  matched: boolean
}

export interface ContractCase {
  doc_id: string
  title: string
  agreement_type: string
  text: string
  findings: Finding[]
  gold_spans: GoldSpanLite[]
}

export interface ArmMetrics {
  precision: number
  recall: number
  f1: number
  ci95: [number, number]
}

export interface PerTypeRow {
  clause_type: string
  gold: number
  precision: number
  recall: number
  f1: number
}

export interface Results {
  contracts_processed: number
  n_clause_types: number
  iou_threshold: number
  model: string
  total_gold_spans: number
  arms: {
    keyword: ArmMetrics
    single_shot: ArmMetrics
    pipeline_no_verifier: ArmMetrics
    pipeline_full: ArmMetrics
  }
  agentic_lift_f1: number
  verifier_contribution_f1: number
  iou_threshold_sweep: Record<string, { pipeline_full: number; single_shot: number }>
  per_type: PerTypeRow[]
}

export interface CrossModelArm { p: number; r: number; f1: number; ci: [number, number] }
export interface CrossModel {
  model: string
  n_contracts: number
  auth: string
  single_shot: CrossModelArm
  pipeline_chunked_no_verifier: CrossModelArm
  chunking_lift_f1: number
}

export interface DemoData {
  results: Results
  contracts: ContractCase[]
  cross_model: CrossModel | null
  generated_at: string
}
