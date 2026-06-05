"""Cross-run comparison + paper-table export.

Reads ``metrics.json`` from one or more run directories and emits comparison
tables as Markdown + CSV (LaTeX-friendly) into ``docs/research/generated/``.
Every figure traces back to a run's ``metrics.json`` (no hand-entered numbers).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Columns surfaced in the headline paper table (flattened metric keys).
_HEADLINE = [
    ("config", "config"),
    ("n", "n"),
    ("abstention_rate", "abstention_rate"),
    ("mean_token_f1", "mean_token_f1"),
    ("grounded_answer_rate", "grounded_answer_rate"),
    ("mean_citation_precision_proxy", "mean_citation_precision_proxy"),
    ("aurc", "abstention_calibration.aurc"),
    ("ece", "abstention_calibration.ece"),
    ("brier", "abstention_calibration.brier"),
    ("sel_acc", "abstention_calibration.selective_accuracy"),
    ("false_answer", "abstention_calibration.false_answer_rate"),
    ("latency_p50_ms", "trace.latency_p50_ms"),
]


def _dig(d: dict[str, Any], dotted: str) -> Any:
    cur: Any = d
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _load_run(run_dir: str | Path) -> dict[str, Any]:
    p = Path(run_dir)
    metrics = json.loads((p / "metrics.json").read_text(encoding="utf-8"))
    name = p.name
    snap = p / "config.snapshot.yaml"
    if snap.exists():
        import yaml

        cfg = yaml.safe_load(snap.read_text(encoding="utf-8")) or {}
        name = cfg.get("name", name)
    return {"config": name, "run_dir": str(p), "metrics": metrics}


def compare(run_dirs: Sequence[str | Path]) -> dict[str, Any]:
    rows = []
    for rd in run_dirs:
        run = _load_run(rd)
        m = run["metrics"]
        row = {"config": run["config"], "run_dir": run["run_dir"]}
        for label, key in _HEADLINE:
            if label == "config":
                continue
            row[label] = _dig(m, key) if "." in key else m.get(key)
        rows.append(row)
    return {"rows": rows, "columns": [label for label, _ in _HEADLINE]}


def _fmt(v: Any) -> str:
    if v is None:
        return "TODO"  # honest: metric not present in this run
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def export_paper_tables(run_dirs: Sequence[str | Path], out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    comp = compare(run_dirs)
    cols = comp["columns"]

    # CSV
    csv_path = out / "results_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in comp["rows"]:
            w.writerow([_fmt(r.get(c)) for c in cols])

    # Markdown
    md_path = out / "results_table.md"
    lines = [
        "# Generated results table",
        "",
        "_Auto-generated from run metrics.json — do not hand-edit._",
        "",
    ]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for r in comp["rows"]:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # LaTeX (booktabs) — placeholder-safe, TODO where metric missing
    tex_path = out / "results_table.tex"
    tex = [
        "% Auto-generated from run metrics.json — do not hand-edit.",
        "\\begin{tabular}{l" + "r" * (len(cols) - 1) + "}",
        "\\toprule",
        " & ".join(c.replace("_", "\\_") for c in cols) + " \\\\",
        "\\midrule",
    ]
    for r in comp["rows"]:
        tex.append(" & ".join(_fmt(r.get(c)).replace("_", "\\_") for c in cols) + " \\\\")
    tex += ["\\bottomrule", "\\end{tabular}"]
    tex_path.write_text("\n".join(tex) + "\n", encoding="utf-8")

    return {"csv": str(csv_path), "md": str(md_path), "tex": str(tex_path)}
