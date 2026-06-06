"""Analyze your own contract locally.

    FIELDAGENT_LIVE=1 python cli/analyze.py path/to/contract.txt

Reads a plain-text contract, runs the full agentic pipeline on a live DeepSeek
client, and prints severity-sorted findings. Refuses to run without
FIELDAGENT_LIVE=1 so it can never spend by accident; reads keys from env only.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from fieldagent.pipeline import analyze, run_summary

_SEV_COLOR = {"high": "\033[91m", "medium": "\033[93m", "low": "\033[96m"}
_RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flag risk-bearing clauses in a contract.")
    ap.add_argument("contract", type=Path, help="path to a plain-text contract")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    if os.environ.get("FIELDAGENT_LIVE") != "1":
        print("Refusing to run: set FIELDAGENT_LIVE=1 to opt in to paid DeepSeek calls.\n"
              "  export OSSLLM_API_KEY=...   # or source your DeepSeek env file\n"
              "  FIELDAGENT_LIVE=1 python cli/analyze.py <contract.txt>", file=sys.stderr)
        return 2
    if not args.contract.exists():
        print(f"no such file: {args.contract}", file=sys.stderr)
        return 1

    from core.deepseek_client import DeepSeekClient  # lazy: needs key

    text = args.contract.read_text(errors="replace")
    client = DeepSeekClient()
    model = os.environ.get("OSSLLM_MODEL", "deepseek-chat")
    findings = analyze(client, text, model=model)

    summary = run_summary(findings)
    print(f"\n{args.contract.name}: {summary['n_findings']} risk-bearing clauses "
          f"(high={summary['by_severity']['high']} "
          f"medium={summary['by_severity']['medium']} "
          f"low={summary['by_severity']['low']})\n")
    for f in findings:
        c = "" if args.no_color else _SEV_COLOR.get(f.severity, "")
        r = "" if args.no_color else _RESET
        print(f"{c}[{f.severity.upper():6}]{r} {f.clause_type}  "
              f"(conf {f.confidence:.2f}, chars {f.start}-{f.end})")
        print(f"         risk: {f.risk_note}")
        snippet = f.span_text.strip().replace("\n", " ")
        print(f"         span: \"{snippet[:160]}{'…' if len(snippet) > 160 else ''}\"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
