# FieldAgent — detection results

Held-out CUAD contracts: **20** · clause types: **15** · IoU threshold: **0.5** · model: `deepseek-v4-pro`

| Arm | Precision | Recall | F1 | 95% CI (F1) |
|---|---|---|---|---|
| Keyword/regex floor | 0.490 | 0.257 | **0.337** | [0.275, 0.392] |
| Single-shot LLM (baseline) | 0.700 | 0.073 | **0.133** | [0.018, 0.282] |
| Pipeline − verifier (chunked) | 0.721 | 0.461 | **0.562** | [0.473, 0.654] |
| **Pipeline (full, agentic)** | 0.741 | 0.435 | **0.548** | [0.460, 0.637] |

**Agentic lift** (full − single-shot): **+0.415 F1**  ·  **Verifier contribution** (full − no-verifier): **-0.014 F1** (precision 0.721→0.741)

## Per-clause-type F1 (full pipeline)

| Clause type | Gold | P | R | F1 |
|---|---|---|---|---|
| Cap On Liability | 32 | 0.78 | 0.22 | 0.34 |
| Ip Ownership Assignment | 23 | 0.75 | 0.26 | 0.39 |
| Anti-Assignment | 20 | 0.61 | 0.55 | 0.58 |
| License Grant | 19 | 0.75 | 0.63 | 0.69 |
| Non-Compete | 15 | 0.88 | 0.47 | 0.61 |
| Exclusivity | 14 | 0.89 | 0.57 | 0.70 |
| Termination For Convenience | 12 | 0.64 | 0.58 | 0.61 |
| Change Of Control | 11 | 1.00 | 0.55 | 0.71 |
| Renewal Term | 10 | 0.83 | 0.50 | 0.62 |
| Liquidated Damages | 9 | 0.33 | 0.11 | 0.17 |
| Audit Rights | 9 | 0.86 | 0.67 | 0.75 |
| Uncapped Liability | 6 | 0.40 | 0.33 | 0.36 |
| No-Solicit Of Employees | 6 | 0.75 | 0.50 | 0.60 |
| Source Code Escrow | 3 | 0.00 | 0.00 | 0.00 |
| Most Favored Nation | 2 | 1.00 | 1.00 | 1.00 |

## IoU-threshold sensitivity (F1)

| IoU | Single-shot | Pipeline (full) |
|---|---|---|
| 0.1 | 0.171 | 0.653 |
| 0.3 | 0.161 | 0.640 |
| 0.5 | 0.133 | 0.548 |
| 0.7 | 0.085 | 0.462 |
