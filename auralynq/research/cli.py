"""``auralynq-research`` — Phase 2 experiment CLI.

Commands:
  run               run a config on a dataset -> runs/<id>/
  list-datasets     show registered benchmark adapters + availability
  list-models       detect Ollama + show profile model availability (no pulls)
  evaluate          recompute aggregate metrics for a run
  compare           compare metrics across runs
  export-paper-tables   write generated CSV/MD/LaTeX tables from runs
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="auralynq-research",
    help="Auralynq Phase 2 — observable agentic RAG evaluation.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def run(
    config: Path = typer.Option(..., "--config", help="Research config YAML."),
    dataset: str = typer.Option("mini", "--dataset", help="Dataset name (or 'mini')."),
    output: Path = typer.Option(..., "--output", help="Run output dir, e.g. runs/<id>."),
    limit: int | None = typer.Option(None, "--limit", help="Cap #examples."),
    calibrator: Path | None = typer.Option(
        None, "--calibrator", help="Fitted calibrator JSON (calibrated mode)."
    ),
) -> None:
    """Run a config on a dataset and write a provenanced run directory."""
    from auralynq.research.runner import run as run_experiment

    out = run_experiment(
        str(config),
        dataset,
        str(output),
        limit=limit,
        calibrator_path=str(calibrator) if calibrator else None,
    )
    console.print_json(json.dumps(out["metrics"]))
    console.print(f"[green]✓[/] run written to {out['run_dir']} ({out['n']} examples)")


@app.command()
def calibrate(
    run: Path = typer.Option(..., "--run", help="Run dir to fit the calibrator from."),
    output: Path = typer.Option(..., "--output", help="Where to write calibrator JSON."),
    holdout: float = typer.Option(0.0, "--holdout", help="Test fraction (0=in-sample)."),
) -> None:
    """Fit a learned calibrator from a run's traces; report ECE/AURC before->after."""
    from auralynq.research.calibrate import fit_and_save

    report = fit_and_save(str(run), str(output), holdout=holdout)
    console.print_json(json.dumps(report))


@app.command("list-datasets")
def list_datasets() -> None:
    """List registered benchmark adapters and whether local files are present."""
    from auralynq.research.datasets import list_datasets as _ld

    table = Table(title="Research datasets")
    for col in ("name", "available", "source", "license"):
        table.add_column(col)
    for r in _ld():
        table.add_row(str(r["name"]), str(r["available"]), str(r["source"]), str(r["license"]))
    console.print(table)


@app.command("list-models")
def list_models() -> None:
    """Detect Ollama and show profile model availability (never pulls)."""
    from auralynq.research.models import list_models_report

    rep = list_models_report()
    console.print(
        f"Ollama reachable={rep['reachable']} at {rep['base_url']} | "
        f"RAM={rep['total_ram_gb']}GB | auto_pull={rep['auto_pull']}"
    )
    profiles: dict = rep["profiles"]  # type: ignore[assignment]
    for profile, rows in profiles.items():
        table = Table(title=f"profile: {profile}")
        for col in ("tag", "present", "likely_fits", "approx_gb", "pull_cmd"):
            table.add_column(col)
        for r in rows:
            table.add_row(
                str(r["tag"]),
                str(r["present"]),
                str(r["likely_fits"]),
                str(r["approx_gb"]),
                str(r["pull_cmd"] or ""),
            )
        console.print(table)
    if not rep["reachable"]:
        console.print("[yellow]Ollama not reachable — start it or set AURALYNQ_LLM__BASE_URL.[/]")


@app.command()
def evaluate(run: Path = typer.Option(..., "--run", help="Run directory.")) -> None:
    """Recompute aggregate metrics for a run from its traces."""
    from auralynq.research.runner import evaluate_run

    agg = evaluate_run(str(run))
    console.print_json(json.dumps(agg))


@app.command()
def compare(
    runs: list[str] = typer.Option(..., "--runs", help="Run dirs (repeat or glob)."),
) -> None:
    """Compare metrics across runs (supports globs)."""
    from auralynq.research.reporting import compare as _compare

    expanded = _expand(runs)
    comp = _compare(expanded)
    table = Table(title="Run comparison")
    for c in comp["columns"]:
        table.add_column(c)
    for r in comp["rows"]:
        table.add_row(*[str(r.get(c, "")) for c in comp["columns"]])
    console.print(table)


@app.command("export-paper-tables")
def export_paper_tables(
    runs: list[str] = typer.Option(..., "--runs", help="Run dirs (repeat or glob)."),
    output: Path = typer.Option(Path("docs/research/generated"), "--output", help="Output dir."),
) -> None:
    """Write generated CSV/MD/LaTeX result tables from runs."""
    from auralynq.research.reporting import export_paper_tables as _export

    paths = _export(_expand(runs), str(output))
    console.print_json(json.dumps(paths))


def _expand(runs: list[str]) -> list[str]:
    out: list[str] = []
    for r in runs:
        hits = sorted(glob.glob(r))
        out.extend(hits if hits else [r])
    return [p for p in out if Path(p).is_dir()]


if __name__ == "__main__":
    app()
