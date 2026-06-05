"""Tests for the Phase 2 research layer (offline, deterministic, $0).

Covers the brief's required areas: dataset schema normalization, config loading,
evidence-sufficiency features, calibration schema, retrieval/abstention/citation
metrics, trace serialization, Ollama detection (unavailable/missing), adapter
mock data, paper-table export, and the no-secrets-in-run-metadata guarantee.
"""

from __future__ import annotations

import json

import pytest
from auralynq.research import metrics as M
from auralynq.research.calibration import (
    TemperatureScaler,
    aurc,
    brier_score,
    expected_calibration_error,
    get_calibrator,
)
from auralynq.research.config import ResearchConfig, load_config
from auralynq.research.datasets import get_adapter, list_datasets
from auralynq.research.datasets.base import NormalizedExample
from auralynq.research.datasets.crag_adapter import CRAGAdapter
from auralynq.research.evaluators import agreement_report, offline_judges
from auralynq.research.evaluators.base import JudgeInput, Verdict, cohen_kappa
from auralynq.research.evidence_sufficiency import (
    EvidenceSufficiencyController,
    SufficiencyDecision,
    extract_features,
)
from auralynq.research.trace import ResearchTrace, load_traces, write_trace


# ----------------------------------------------------------------- configs ---
def test_all_shipped_configs_load():
    import glob

    paths = sorted(glob.glob("configs/research/*.yaml"))
    assert len(paths) == 9
    for p in paths:
        cfg = load_config(p)
        assert cfg.name
        assert cfg.retrieval.final_k > 0
        # rerank env override is consistent with the flag
        env = cfg.env_overrides()
        assert env["AURALYNQ_RERANK__PROVIDER"] in ("auto", "none")


def test_config_env_overrides_and_helpers():
    cfg = ResearchConfig(name="t")
    cfg.retrieval.mode = "full_agentic"
    assert cfg.use_graph and cfg.use_reranker
    cfg2 = ResearchConfig(name="d")
    cfg2.retrieval.mode = "dense"
    cfg2.retrieval.keyword = False
    assert not cfg2.use_graph and not cfg2.use_reranker and not cfg2.use_keyword


def test_config_rejects_unknown_keys():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResearchConfig.from_dict({"name": "x", "bogus_field": 1})


# ---------------------------------------------------------------- datasets ---
def test_mini_dataset_normalization_and_abstention_items():
    examples = get_adapter("mini").load()
    assert len(examples) == 6
    assert all(isinstance(e, NormalizedExample) for e in examples)
    assert sum(e.requires_abstention for e in examples) == 2  # honest unanswerables
    e = examples[0]
    assert e.question and e.question_id and e.metadata["dataset"] == "custom_corpus"


def test_adapter_mock_records_normalize():
    raw = [
        {"interaction_id": "q1", "query": "What is X?", "answer": "X is Y.", "domain": "finance"},
        {"interaction_id": "q2", "query": "Unknown?", "answer": "invalid"},
    ]
    out = CRAGAdapter().normalize_records(raw)
    assert out[0].question == "What is X?"
    assert out[0].domain == "finance"
    assert out[1].requires_abstention is True  # 'invalid' -> abstain label


def test_list_datasets_reports_availability():
    rows = list_datasets()
    names = {r["name"] for r in rows}
    assert {"mini", "crag", "ragbench", "mirage", "t2_ragbench", "ares"} <= names
    mini = next(r for r in rows if r["name"] == "mini")
    assert mini["available"] is True


# -------------------------------------------------------- evidence/suff. -----
def test_sufficiency_features_and_decision_schema():
    strong = extract_features(
        {
            "retrieval_scores": [0.9, 0.4],
            "n_supporting_chunks": 3,
            "citation_coverage": 1.0,
            "source_agreement": 0.8,
        }
    )
    esc = EvidenceSufficiencyController(abstain_threshold=0.5)
    d = esc.decide(strong)
    assert isinstance(d, SufficiencyDecision)
    assert d.evidence_sufficient is True and d.abstain is False
    assert 0.0 <= d.confidence <= 1.0 and 0.0 <= d.hallucination_risk <= 1.0
    assert d.calibration_bucket in ("low", "medium", "high")
    assert "features" in d.to_dict() and d.reasons


@pytest.mark.parametrize(
    "signals,expect_abstain",
    [
        ({"retrieval_scores": [], "n_supporting_chunks": 0, "citation_coverage": 0.0}, True),
        (
            {"retrieval_scores": [0.85, 0.5], "n_supporting_chunks": 3, "citation_coverage": 0.0},
            True,
        ),
        (
            {
                "retrieval_scores": [0.8],
                "n_supporting_chunks": 2,
                "citation_coverage": 0.8,
                "language_mismatch": True,
            },
            True,
        ),
        (
            {
                "retrieval_scores": [0.8, 0.7],
                "n_supporting_chunks": 3,
                "citation_coverage": 0.8,
                "contradiction_signal": 0.7,
            },
            True,
        ),
    ],
)
def test_sufficiency_abstains_on_weak_or_risky_evidence(signals, expect_abstain):
    esc = EvidenceSufficiencyController(abstain_threshold=0.5, citation_required=True)
    assert esc.decide(extract_features(signals)).abstain is expect_abstain


# ------------------------------------------------------------- calibration ---
def test_calibration_metrics_ranges_and_schema():
    conf = [0.9, 0.8, 0.6, 0.4, 0.3]
    correct = [1, 1, 0, 0, 0]
    assert 0.0 <= expected_calibration_error(conf, correct) <= 1.0
    assert 0.0 <= brier_score(conf, correct) <= 1.0
    assert 0.0 <= aurc(conf, correct) <= 1.0
    ts = TemperatureScaler().fit(conf, correct)
    assert ts.temperature > 0
    j = ts.to_json()
    assert j["name"] == "temperature" and "temperature" in j
    assert get_calibrator("identity").predict_one(0.7) == 0.7


def test_abstention_metrics_schema():
    out = M.abstention_metrics([0.9, 0.8, 0.4, 0.3], [1, 1, 0, 0], [0, 0, 1, 1])
    for k in (
        "aurc",
        "ece",
        "abstain_ece",
        "brier",
        "false_answer_rate",
        "false_abstention_rate",
        "selective_accuracy",
        "coverage_risk_curve",
    ):
        assert k in out
    assert out["coverage"] == 0.5


# ---------------------------------------------------------------- metrics ----
def test_generation_and_citation_metrics():
    assert M.token_f1("paris is capital", "the capital is paris") > 0.0
    assert M.exact_match("Paris", "paris") == 1
    g = M.groundedness_proxy("MMR removes redundancy.", ["mmr removes redundant chunks"])
    assert 0.0 <= g <= 1.0
    cm = M.citation_metrics_proxy("X is Y.", [{"text": "x is y indeed"}], ["x is y indeed"])
    assert set(cm) == {
        "citation_coverage",
        "citation_precision_proxy",
        "citation_recall_proxy",
    }


def test_retrieval_metrics_reuse():
    cases = [({"pathrag.md"}, ["pathrag.md", "other.md"])]
    out = M.retrieval_metrics(cases, k=2)
    assert out["recall_at_k"] == 1.0 and out["k"] == 2


# ------------------------------------------------------------------ judges ---
def test_offline_judges_and_agreement():
    inp = JudgeInput(
        question="How does PathRAG prune?",
        answer="PathRAG prunes relational paths with flow-based pruning.",
        contexts=["pathrag prunes relational paths using flow-based pruning"],
        citations=[{"text": "pathrag prunes relational paths using flow-based pruning"}],
        abstained=False,
    )
    verdicts = [j.judge(inp) for j in offline_judges()]
    assert all(isinstance(v, Verdict) and not v.is_ground_truth for v in verdicts)

    a = [Verdict(judge="a", dimension="d", label=x) for x in ["s", "s", "u"]]
    b = [Verdict(judge="b", dimension="d", label=x) for x in ["s", "u", "u"]]
    rep = agreement_report({"heuristic": a, "llm": b})
    assert "krippendorff_alpha" in rep and rep["n_items"] == 3
    assert cohen_kappa(["s", "s"], ["s", "s"]) == 1.0


# ------------------------------------------------------------------- trace ---
def test_trace_serialization_roundtrip(tmp_path):
    tr = ResearchTrace(
        question_id="q/1",
        question="q?",
        retrieval_mode="dense",
        retrieval_scores=[0.8, 0.5],
        evidence_sufficiency={"confidence": 0.7, "hallucination_risk": 0.2, "features": {}},
        abstained=False,
        metrics={"correct": 1, "groundedness_proxy": 0.9},
    )
    p = write_trace(tr, tmp_path)
    assert p.exists()
    loaded = load_traces(tmp_path)
    assert len(loaded) == 1 and loaded[0].question_id == "q/1"
    row = loaded[0].feature_row()
    assert row["top_retrieval_score"] == 0.8 and row["correct"] == 1


# --------------------------------------------------------- model detection ---
def test_ollama_unavailable(monkeypatch):
    import httpx
    from auralynq.research.models import ollama_profiles as op

    def _boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(op.httpx, "get", _boom)
    inv = op.inventory()
    assert inv.reachable is False
    rep = op.list_models_report(inv)
    assert rep["reachable"] is False
    # missing models still produce pull commands (never auto-run)
    assert all(
        r["pull_cmd"] is None or r["pull_cmd"].startswith("ollama pull")
        for rows in rep["profiles"].values()
        for r in rows
    )


def test_ollama_reachable_but_model_missing(monkeypatch):
    from auralynq.research.models import ollama_profiles as op

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "some-other-model:1b"}]}

    monkeypatch.setattr(op.httpx, "get", lambda *a, **k: _Resp())
    inv = op.inventory()
    assert inv.reachable is True
    assert inv.has("llama3.2:3b") is False
    assert op.auto_pull_enabled() is False  # never auto-pull by default


# ----------------------------------------------------- end-to-end + secrets --
def _build_index(corpus_dir):
    from auralynq.pipeline import build_index

    return build_index(corpus_dir, rebuild=True)


def test_runner_end_to_end_and_no_secrets(corpus_dir, tmp_path, monkeypatch):
    # a real (tiny) index from the conftest corpus
    _build_index(corpus_dir)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-thisshouldnotleak-123456")  # must NOT appear

    from auralynq.research.runner import run as run_experiment

    offline = {
        "AURALYNQ_EMBEDDING__PROVIDER": "hash",
        "AURALYNQ_VECTOR__BACKEND": "memory",
        "AURALYNQ_LLM__PROVIDER": "extractive",
        "AURALYNQ_DATA_DIR": str(tmp_path / "data"),
    }
    out_dir = tmp_path / "run1"
    out = run_experiment(
        "configs/research/baseline_vector.yaml",
        "mini",
        str(out_dir),
        extra_env=offline,
    )
    assert out["n"] == 6
    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "provenance.json").exists()
    assert (out_dir / "results.json").exists()
    assert list((out_dir / "traces").glob("*.json"))

    # no secret value anywhere in the run artifacts
    blob = "\n".join(
        (out_dir / f).read_text(encoding="utf-8")
        for f in ("provenance.json", "results.json", "metrics.json")
    )
    blob += (out_dir / "config.snapshot.yaml").read_text(encoding="utf-8")
    assert "sk-thisshouldnotleak" not in blob
    prov = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))
    assert prov["env"]["OPENAI_API_KEY"].startswith("<redacted")


# ================================================================ calibrate ==


def _make_trace(question_id: str, correct: int | None, confidence: float = 0.5) -> ResearchTrace:
    """Minimal ResearchTrace with realistic ESC features for calibration tests."""
    features = {
        "top_k_retrieval_score": 0.8,
        "retrieval_score_margin": 0.3,
        "reranker_score": 0.7,
        "citation_coverage": 1.0,
        "graph_path_reliability": 0.5,
        "source_agreement": 0.9,
        "n_supporting_chunks": 2,
    }
    return ResearchTrace(
        question_id=question_id,
        question="q?",
        retrieval_mode="dense",
        retrieval_scores=[0.8, 0.5],
        evidence_sufficiency={"confidence": confidence, "hallucination_risk": 0.2, "features": features},
        abstained=False,
        metrics={"correct": correct} if correct is not None else {},
    )


def _write_biclass_run(run_dir, n: int = 10) -> None:
    """Write n traces with alternating correct=0/1 labels into run_dir."""
    for i in range(n):
        write_trace(_make_trace(f"q{i}", i % 2, confidence=0.4 + 0.05 * (i % 2)), run_dir)


def test_rows_from_traces_excludes_unlabeled():
    from auralynq.research.calibrate import _rows_from_traces

    traces = [_make_trace("q1", 1), _make_trace("q2", None), _make_trace("q3", 0)]
    feats, conf, correct = _rows_from_traces(traces)
    assert len(feats) == len(conf) == len(correct) == 2
    assert correct == [1, 0]


def test_rows_from_traces_extracts_confidence_and_features():
    from auralynq.research.calibrate import _rows_from_traces

    traces = [_make_trace("q1", 1, confidence=0.75)]
    feats, conf, correct = _rows_from_traces(traces)
    assert conf == [0.75]
    assert feats[0]["top_k_retrieval_score"] == 0.8


def test_fit_calibrator_insufficient_n(tmp_path):
    from auralynq.research.calibrate import fit_calibrator_from_run

    for i in range(3):
        write_trace(_make_trace(f"q{i}", i % 2), tmp_path)
    cal, report = fit_calibrator_from_run(tmp_path)
    assert cal is None
    assert report["status"] == "insufficient_data"
    assert report["n_scored"] == 3


def test_fit_calibrator_single_class(tmp_path):
    from auralynq.research.calibrate import fit_calibrator_from_run

    for i in range(6):
        write_trace(_make_trace(f"q{i}", 0), tmp_path)
    cal, report = fit_calibrator_from_run(tmp_path)
    assert cal is None
    assert report["status"] == "insufficient_data"


def test_fit_calibrator_insample(tmp_path):
    from auralynq.research.calibrate import CALIBRATION_FEATURES, fit_calibrator_from_run

    _write_biclass_run(tmp_path)
    cal, report = fit_calibrator_from_run(tmp_path, holdout=0.0)
    assert cal is not None and cal.fitted
    assert report["status"] == "ok"
    assert report["eval_mode"] == "in-sample"
    assert report["n_scored"] == 10
    assert report["feature_keys"] == CALIBRATION_FEATURES
    for key in ("ece", "brier", "aurc", "n"):
        assert key in report["before_raw"] and key in report["after_learned"]
    assert set(report["delta"]) == {"ece", "brier", "aurc"}


def test_fit_calibrator_holdout(tmp_path):
    from auralynq.research.calibrate import fit_calibrator_from_run

    _write_biclass_run(tmp_path, n=12)
    cal, report = fit_calibrator_from_run(tmp_path, holdout=0.2)
    assert cal is not None
    assert report["status"] == "ok"
    assert "holdout" in report["eval_mode"]
    assert report["before_raw"]["n"] < report["n_scored"]


def test_fit_and_save_writes_json_and_path(tmp_path):
    from auralynq.research.calibrate import fit_and_save

    _write_biclass_run(tmp_path / "run")
    out_path = tmp_path / "cal" / "calibrator.json"
    report = fit_and_save(tmp_path / "run", out_path)
    assert report["status"] == "ok"
    assert "calibrator_path" in report
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["name"] == "logistic"
    assert "coef" in data and "feature_keys" in data


def test_fit_and_save_no_file_on_insufficient_data(tmp_path):
    from auralynq.research.calibrate import fit_and_save

    for i in range(2):
        write_trace(_make_trace(f"q{i}", i % 2), tmp_path / "run")
    out_path = tmp_path / "cal" / "calibrator.json"
    report = fit_and_save(tmp_path / "run", out_path)
    assert report["status"] == "insufficient_data"
    assert "calibrator_path" not in report
    assert not out_path.exists()


# ================================================================= cli =======


def test_cli_list_datasets():
    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app

    result = CliRunner().invoke(research_app, ["list-datasets"])
    assert result.exit_code == 0, result.exception


def test_cli_list_models_unreachable(monkeypatch):
    import httpx
    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app
    from auralynq.research.models import ollama_profiles as op

    def _no_ollama(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(op.httpx, "get", _no_ollama)
    result = CliRunner().invoke(research_app, ["list-models"])
    assert result.exit_code == 0, result.exception


def test_cli_calibrate_insufficient_data(tmp_path):
    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app

    run_dir = tmp_path / "run"
    for i in range(6):
        write_trace(_make_trace(f"q{i}", 0), run_dir)
    out_path = tmp_path / "cal.json"
    result = CliRunner().invoke(research_app, [
        "calibrate",
        "--run", str(run_dir),
        "--output", str(out_path),
    ])
    assert result.exit_code == 0, result.exception
    assert not out_path.exists()


def test_cli_calibrate_ok(tmp_path):
    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app

    run_dir = tmp_path / "run"
    _write_biclass_run(run_dir)
    out_path = tmp_path / "cal.json"
    result = CliRunner().invoke(research_app, [
        "calibrate",
        "--run", str(run_dir),
        "--output", str(out_path),
        "--holdout", "0.0",
    ])
    assert result.exit_code == 0, result.exception
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["name"] == "logistic"


def test_cli_run_wires_params(tmp_path, monkeypatch):
    from pathlib import Path

    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app

    calls: list[dict] = []

    def fake_run(config, dataset, output, limit=None, calibrator_path=None, **kwargs):
        calls.append({"dataset": dataset, "calibrator_path": calibrator_path})
        Path(output).mkdir(parents=True, exist_ok=True)
        return {"metrics": {"abstention_rate": 0.0}, "run_dir": output, "n": 3}

    monkeypatch.setattr("auralynq.research.runner.run", fake_run)
    result = CliRunner().invoke(research_app, [
        "run",
        "--config", "configs/research/full_agentic.yaml",
        "--dataset", "mini",
        "--output", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0, result.exception
    assert len(calls) == 1 and calls[0]["dataset"] == "mini"
    assert calls[0]["calibrator_path"] is None


def test_cli_run_passes_calibrator_path(tmp_path, monkeypatch):
    from pathlib import Path

    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app

    calls: list[dict] = []

    def fake_run(config, dataset, output, limit=None, calibrator_path=None, **kwargs):
        calls.append({"calibrator_path": calibrator_path})
        Path(output).mkdir(parents=True, exist_ok=True)
        return {"metrics": {}, "run_dir": output, "n": 0}

    monkeypatch.setattr("auralynq.research.runner.run", fake_run)
    fake_cal = tmp_path / "cal.json"
    fake_cal.write_text("{}")
    result = CliRunner().invoke(research_app, [
        "run",
        "--config", "configs/research/full_agentic.yaml",
        "--dataset", "mini",
        "--output", str(tmp_path / "out"),
        "--calibrator", str(fake_cal),
    ])
    assert result.exit_code == 0, result.exception
    assert calls[0]["calibrator_path"] == str(fake_cal)


def test_cli_evaluate_wires_params(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from auralynq.research.cli import app as research_app

    called_with: list[str] = []
    monkeypatch.setattr(
        "auralynq.research.runner.evaluate_run",
        lambda run_dir: (called_with.append(run_dir), {"abstention_rate": 0.5, "n": 4})[1],
    )
    result = CliRunner().invoke(research_app, ["evaluate", "--run", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    assert str(tmp_path) in called_with


def test_export_paper_tables(corpus_dir, tmp_path):
    _build_index(corpus_dir)
    from auralynq.research.reporting import export_paper_tables
    from auralynq.research.runner import run as run_experiment

    offline = {
        "AURALYNQ_EMBEDDING__PROVIDER": "hash",
        "AURALYNQ_VECTOR__BACKEND": "memory",
        "AURALYNQ_LLM__PROVIDER": "extractive",
        "AURALYNQ_DATA_DIR": str(tmp_path / "data"),
    }
    rd = tmp_path / "runA"
    run_experiment("configs/research/baseline_vector.yaml", "mini", str(rd), extra_env=offline)
    paths = export_paper_tables([str(rd)], str(tmp_path / "gen"))
    assert all(__import__("pathlib").Path(p).exists() for p in paths.values())
    md = __import__("pathlib").Path(paths["md"]).read_text(encoding="utf-8")
    assert "baseline_vector" in md
