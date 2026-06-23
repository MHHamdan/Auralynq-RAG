"""ModelFit scoring system for Auralynq ModelFit Index.

Produces a composite ModelFit Score (0-100) from hardware fit, speed fit,
RAG fit, task fit, and deployment fit sub-scores. All scores clearly
distinguish estimated from measured values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from auralynq.modelfit.hardware import HardwareProfile
from auralynq.modelfit.model_metadata import ModelMetadata
from auralynq.modelfit.resource_estimator import (
    ResourceEstimate,
    estimate_resources,
    recommend_quantization,
)

ScoreLabel = Literal[
    "Excellent fit", "Recommended", "Usable with limits", "Not recommended", "Does not fit"
]


def _label(score: float) -> ScoreLabel:
    if score >= 85:
        return "Excellent fit"
    if score >= 70:
        return "Recommended"
    if score >= 50:
        return "Usable with limits"
    if score >= 30:
        return "Not recommended"
    return "Does not fit"


@dataclass
class BenchmarkSnapshot:
    """Optional measured benchmark results. When absent, estimates are used."""
    avg_tok_per_sec: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    time_to_first_token_ms: float | None = None
    peak_memory_gb: float | None = None
    citation_coverage: float | None = None
    groundedness: float | None = None
    abstention_accuracy: float | None = None
    is_measured: bool = True  # False if coming from community/self-reported data

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_tok_per_sec": self.avg_tok_per_sec,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "peak_memory_gb": self.peak_memory_gb,
            "citation_coverage": self.citation_coverage,
            "groundedness": self.groundedness,
            "abstention_accuracy": self.abstention_accuracy,
            "is_measured": self.is_measured,
        }


@dataclass
class ModelFitScore:
    model_id: str
    overall_score: float
    hardware_fit: float
    speed_fit: float
    rag_fit: float
    task_fit: float
    deployment_fit: float
    label: ScoreLabel
    best_quantization: str
    reason: str
    resource_estimate: ResourceEstimate | None
    benchmark: BenchmarkSnapshot | None
    estimate_used: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "overall_score": round(self.overall_score, 1),
            "hardware_fit": round(self.hardware_fit, 1),
            "speed_fit": round(self.speed_fit, 1),
            "rag_fit": round(self.rag_fit, 1),
            "task_fit": round(self.task_fit, 1),
            "deployment_fit": round(self.deployment_fit, 1),
            "label": self.label,
            "best_quantization": self.best_quantization,
            "reason": self.reason,
            "resource_estimate": (
                self.resource_estimate.to_dict() if self.resource_estimate else None
            ),
            "benchmark": self.benchmark.to_dict() if self.benchmark else None,
            "estimate_used": self.estimate_used,
            "warnings": self.warnings,
        }


# ── Sub-score calculators ─────────────────────────────────────────────────────

def _hardware_fit_score(
    resource: ResourceEstimate,
    hw: HardwareProfile,
) -> float:
    """Score 0-100: how comfortably the model fits the hardware."""
    base = {"comfortable": 95.0, "tight": 65.0, "not_recommended": 25.0, "impossible": 0.0}
    score = base.get(resource.fit_level, 0.0)

    # Bonus for matching backend
    if hw.cuda_available or hw.metal_available or hw.rocm_available:
        score = min(100.0, score + 5.0)

    # Disk penalty
    if hw.disk_free_gb < resource.estimated_disk_gb * 1.5:
        score = max(0.0, score - 10.0)

    return round(score, 1)


def _speed_fit_score(
    params_b: float | None,
    hw: HardwareProfile,
    benchmark: BenchmarkSnapshot | None,
    quantization: str,
) -> tuple[float, bool]:
    """Score 0-100 for speed, plus whether score came from measurements."""
    if benchmark and benchmark.avg_tok_per_sec is not None:
        tps = benchmark.avg_tok_per_sec
        # Scale: 50+ tok/s → 100, 20 tok/s → 70, 5 tok/s → 40, <2 → 15
        if tps >= 50:
            return 100.0, True
        if tps >= 20:
            return round(70 + (tps - 20) / 30 * 30, 1), True
        if tps >= 5:
            return round(40 + (tps - 5) / 15 * 30, 1), True
        return round(max(15.0, tps * 3), 1), True

    # Estimate from hardware + model size
    if params_b is None:
        return 50.0, False  # unknown model size → neutral

    has_gpu = hw.cuda_available or hw.metal_available or hw.rocm_available
    vram = hw.total_vram_gb

    # Very rough tok/s heuristics — labelled as ESTIMATED
    if not has_gpu:
        # CPU-only: typically 2-15 tok/s depending on quantization and cores
        cpu_tps = max(1.0, 40.0 / params_b * (hw.cpu_cores_logical / 8.0))
        return round(min(40.0, cpu_tps * 10), 1), False

    # GPU: rough estimate based on VRAM bandwidth class
    if vram >= 24:
        gpu_tps = 60.0 / (params_b / 8.0)
    elif vram >= 12:
        gpu_tps = 30.0 / (params_b / 8.0)
    elif vram >= 8:
        gpu_tps = 20.0 / (params_b / 8.0)
    else:
        gpu_tps = 10.0 / (params_b / 8.0)

    score = min(100.0, gpu_tps * 2)
    return round(max(10.0, score), 1), False


def _rag_fit_score(
    model: ModelMetadata,
    benchmark: BenchmarkSnapshot | None,
) -> float:
    """Score 0-100: how well the model suits RAG tasks."""
    if benchmark:
        parts = []
        if benchmark.groundedness is not None:
            parts.append(benchmark.groundedness * 100)
        if benchmark.citation_coverage is not None:
            parts.append(benchmark.citation_coverage * 100)
        if benchmark.abstention_accuracy is not None:
            parts.append(benchmark.abstention_accuracy * 100)
        if parts:
            return round(sum(parts) / len(parts), 1)

    # Heuristic from model metadata
    score = 60.0  # baseline
    if "rag" in model.tasks:
        score += 10.0
    if model.tool_calling:
        score += 5.0
    if model.context_length and model.context_length >= 32768:
        score += 10.0
    if model.family in ("llama", "qwen", "mistral"):
        score += 5.0
    if model.parameter_count_b and model.parameter_count_b >= 7.0:
        score += 5.0
    return round(min(90.0, score), 1)


def _task_fit_score(model: ModelMetadata, requested_tasks: list[str]) -> float:
    """Score 0-100: fraction of requested tasks covered by the model."""
    if not requested_tasks:
        return 75.0  # no specific task requested → neutral
    covered = sum(1 for t in requested_tasks if t in model.tasks)
    return round((covered / len(requested_tasks)) * 100, 1)


def _deployment_fit_score(model: ModelMetadata, hw: HardwareProfile) -> float:
    """Score 0-100: licensing, availability, and deployment ease."""
    score = 50.0

    # Ollama availability — easiest to deploy
    if model.source == "ollama":
        score += 25.0
        if hw.ollama_available:
            score += 10.0
    elif model.source == "local":
        score += 20.0
    elif model.source == "huggingface":
        score += 15.0
        if hw.hf_available:
            score += 5.0

    # Open license bonus
    if model.license.lower() in ("apache-2.0", "mit", "apache 2.0"):
        score += 10.0
    elif model.license.lower() in (
        "llama 3.1 community", "llama 3.2 community", "llama 3.3 community"
    ):
        score += 5.0

    # Gated model penalty
    if model.gated:
        score -= 15.0

    return round(min(100.0, max(0.0, score)), 1)


# ── Main scoring function ─────────────────────────────────────────────────────

_WEIGHTS = {
    "hardware": 0.30,
    "speed": 0.20,
    "rag": 0.25,
    "task": 0.15,
    "deployment": 0.10,
}


def score_model(
    model: ModelMetadata,
    hw: HardwareProfile,
    quantization: str | None = None,
    requested_tasks: list[str] | None = None,
    benchmark: BenchmarkSnapshot | None = None,
    context_tokens: int = 4096,
) -> ModelFitScore:
    """Compute a full ModelFit Score for a model on given hardware."""
    warnings: list[str] = []

    params_b = model.parameter_count_b
    best_quant = quantization or recommend_quantization(
        params_b or 7.0,
        hw.total_vram_gb,
        hw.ram_gb,
    )

    resource: ResourceEstimate | None = None
    hw_score = 50.0
    if params_b is not None:
        resource = estimate_resources(
            model_id=model.model_id,
            params_b=params_b,
            quantization=best_quant,
            available_vram_gb=hw.total_vram_gb,
            available_ram_gb=hw.ram_gb,
            context_tokens=context_tokens,
        )
        hw_score = _hardware_fit_score(resource, hw)
    else:
        warnings.append("Parameter count unknown — hardware fit score is approximate.")

    speed_score, speed_measured = _speed_fit_score(params_b, hw, benchmark, best_quant)
    rag_score = _rag_fit_score(model, benchmark)
    task_score = _task_fit_score(model, requested_tasks or [])
    deploy_score = _deployment_fit_score(model, hw)

    overall = (
        hw_score * _WEIGHTS["hardware"]
        + speed_score * _WEIGHTS["speed"]
        + rag_score * _WEIGHTS["rag"]
        + task_score * _WEIGHTS["task"]
        + deploy_score * _WEIGHTS["deployment"]
    )

    estimate_used = benchmark is None or not speed_measured
    if estimate_used:
        warnings.append(
            "Speed score uses estimates. Run a benchmark for measured tok/s."
        )
    if benchmark and not benchmark.is_measured:
        warnings.append(
            "Benchmark data is self-reported / community-contributed — treat as approximate."
        )

    label = _label(overall)
    reason = _build_reason(model, best_quant, hw_score, overall, resource)

    if resource:
        warnings.extend(resource.warnings)

    return ModelFitScore(
        model_id=model.model_id,
        overall_score=round(overall, 1),
        hardware_fit=hw_score,
        speed_fit=speed_score,
        rag_fit=rag_score,
        task_fit=task_score,
        deployment_fit=deploy_score,
        label=label,
        best_quantization=best_quant,
        reason=reason,
        resource_estimate=resource,
        benchmark=benchmark,
        estimate_used=estimate_used,
        warnings=warnings,
    )


def _build_reason(
    model: ModelMetadata,
    quant: str,
    hw_score: float,
    overall: float,
    resource: ResourceEstimate | None,
) -> str:
    parts: list[str] = []
    if hw_score >= 85:
        parts.append(f"Fits comfortably in available memory at {quant}.")
    elif hw_score >= 65:
        parts.append(f"Fits tightly at {quant} — avoid long contexts.")
    else:
        parts.append(f"May not fit at {quant} — consider a smaller model or lower quantization.")

    if model.parameter_count_b:
        parts.append(f"{model.parameter_count_b}B parameter model.")
    if "rag" in model.tasks:
        parts.append("Supports RAG tasks.")
    if model.tool_calling:
        parts.append("Supports tool calling / agents.")
    if overall >= 85:
        parts.append("Overall: excellent fit.")
    elif overall >= 70:
        parts.append("Overall: recommended for this hardware.")

    return " ".join(parts)
