#!/usr/bin/env python3
"""Phase 2 smoke experiment — fast, offline, $0, deterministic.

NOT a paper result. This validates the research plumbing end-to-end on a tiny
synthetic corpus + the built-in `mini` benchmark, comparing:

  1. baseline_vector  — dense retrieval, no abstention
  2. full_agentic     — agentic pipeline + Evidence Sufficiency Controller

Forces offline providers (hash embeddings, in-memory store, extractive LLM) so it
runs anywhere with no downloads and no keys. Writes:
  runs/smoke_<ts>/<variant>/{results,metrics,provenance}.json + traces/
  docs/research/generated/smoke_summary.md   (clearly labeled SMOKE VALIDATION)
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# A tiny corpus that grounds the answerable `mini` questions. The unanswerable
# mini questions (Atlantis GDP, Zibblecorp CEO) are deliberately NOT covered, so
# honest abstention is exercised.
_CORPUS = {
    "pathrag.md": (
        "PathRAG prunes relational paths using flow-based resource-allocation "
        "pruning over the knowledge graph. It converts key relational paths into "
        "text for prompting and reduces redundancy."
    ),
    "retrieval.md": (
        "Auralynq removes redundant retrieved chunks using maximal marginal "
        "relevance (MMR). Hybrid fusion combines dense and sparse results with "
        "reciprocal rank fusion using an rrf_k constant of 60."
    ),
    "systems.md": (
        "Auralynq supports two vector store backends: Qdrant for production and an "
        "in-memory store for local and test use."
    ),
}


def _setup_env(data_dir: Path) -> None:
    os.environ["AURALYNQ_DOTENV_DISABLED"] = "1"  # never read host .env / secrets
    os.environ["AURALYNQ_DATA_DIR"] = str(data_dir)
    os.environ["AURALYNQ_EMBEDDING__PROVIDER"] = "hash"
    os.environ["AURALYNQ_VECTOR__BACKEND"] = "memory"
    os.environ["AURALYNQ_LLM__PROVIDER"] = "extractive"
    os.environ["AURALYNQ_TELEMETRY__ENABLED"] = "false"
    os.environ["AURALYNQ_SEED"] = "42"


def _write_corpus(corpus_dir: Path) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for name, text in _CORPUS.items():
        (corpus_dir / name).write_text(text, encoding="utf-8")


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    data_dir = repo / "data" / "research_smoke"
    _setup_env(data_dir)

    # late imports so env is applied before settings are read
    from auralynq.config import reload_settings
    from auralynq.pipeline import build_index
    from auralynq.research.reporting import compare
    from auralynq.research.runner import run as run_experiment

    reload_settings()
    corpus_dir = data_dir / "corpus"
    _write_corpus(corpus_dir)
    stats = build_index(corpus_dir, rebuild=True)
    print(f"[smoke] indexed: {stats}")

    # Force offline providers regardless of each config's `auto` values.
    offline_env = {
        "AURALYNQ_EMBEDDING__PROVIDER": "hash",
        "AURALYNQ_VECTOR__BACKEND": "memory",
        "AURALYNQ_LLM__PROVIDER": "extractive",
        "AURALYNQ_DATA_DIR": str(data_dir),
        "AURALYNQ_TELEMETRY__ENABLED": "false",
    }
    run_root = repo / "runs" / f"smoke_{ts}"
    variants = ["baseline_vector", "full_agentic"]
    summaries = []
    for v in variants:
        cfg = repo / "configs" / "research" / f"{v}.yaml"
        out = run_experiment(str(cfg), "mini", str(run_root / v), extra_env=offline_env)
        summaries.append((v, str(run_root / v), out["metrics"]))
        print(f"[smoke] {v}: abstention_rate={out['metrics'].get('abstention_rate')}")

    comp = compare([rd for _, rd, _ in summaries])
    _write_summary(repo, ts, summaries, comp)
    print("[smoke] summary -> docs/research/generated/smoke_summary.md")
    print(f"[smoke] runs    -> {run_root}")
    return 0


def _write_summary(repo: Path, ts: str, summaries, comp) -> None:
    out = repo / "docs" / "research" / "generated" / "smoke_summary.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Smoke Experiment Summary",
        "",
        "> **SMOKE VALIDATION ONLY — NOT A PAPER RESULT.** Tiny synthetic corpus, "
        "the 6-item built-in `mini` benchmark, offline hash embeddings + extractive "
        "LLM. It validates that the research pipeline runs end-to-end and that "
        "abstention is honest. Real results require the benchmark datasets, real "
        "models, and larger N (see `experimental-protocol.md`).",
        "",
        f"- Generated (UTC): `{ts}`",
        f"- Variants: {', '.join(v for v, _, _ in summaries)}",
        "",
        "## Headline comparison",
        "",
        "| " + " | ".join(comp["columns"]) + " |",
        "| " + " | ".join("---" for _ in comp["columns"]) + " |",
    ]
    for r in comp["rows"]:
        lines.append("| " + " | ".join(str(r.get(c, "TODO")) for c in comp["columns"]) + " |")
    lines += [
        "",
        "## Per-variant metrics (excerpt)",
        "",
    ]
    for v, rd, m in summaries:
        ac = m.get("abstention_calibration", {})
        lines.append(
            f"- **{v}**: abstention_rate={m.get('abstention_rate')}, "
            f"grounded_answer_rate={m.get('grounded_answer_rate')}, "
            f"mean_token_f1={m.get('mean_token_f1')}, "
            f"AURC={ac.get('aurc')}, ECE={ac.get('ece')}  ·  `{rd}`"
        )
    lines += [
        "",
        "_Numbers come straight from each run's `metrics.json`; nothing hand-edited._",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
