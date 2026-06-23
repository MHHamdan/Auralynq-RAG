"""VRAM/RAM and quantization resource estimator for Auralynq ModelFit Index.

These are ESTIMATES based on published memory formulas and community observations.
They are labelled as estimates throughout. Measured benchmark results always
override estimates when available.

Formula basis:
  VRAM ~ (params_b x bytes_per_param) + kv_cache_overhead + framework_overhead
  bytes_per_param: fp16=2, bf16=2, int8=1, q8≈1, q6≈0.75, q5≈0.625,
                   q4≈0.5, q3≈0.375, q2≈0.25
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FitLevel = Literal["comfortable", "tight", "not_recommended", "impossible"]

# bytes per parameter per quantization level
_BYTES_PER_PARAM: dict[str, float] = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "int8": 1.0,
    "q8": 1.0,
    "q6_k": 0.75,
    "q5_k": 0.625,
    "q5_1": 0.6875,
    "q4_k": 0.5,
    "q4_0": 0.5,
    "q3_k": 0.375,
    "q2_k": 0.25,
}

# Framework + activation overhead in GB (rough constant per model load)
_FRAMEWORK_OVERHEAD_GB = 1.0

# KV cache per 1K context tokens per 1B params (rough heuristic)
_KV_CACHE_GB_PER_1K_TOKENS_PER_1B = 0.003


def _kv_cache_gb(params_b: float, context_tokens: int, quantization: str) -> float:
    """Estimate KV cache size for a given context length."""
    factor = 1.0 if quantization in ("fp16", "bf16", "fp32") else 0.5
    return params_b * (context_tokens / 1000) * _KV_CACHE_GB_PER_1K_TOKENS_PER_1B * factor


def estimate_vram_gb(params_b: float, quantization: str, context_tokens: int = 4096) -> float:
    bpp = _BYTES_PER_PARAM.get(quantization, 0.5)
    model_gb = params_b * 1e9 * bpp / (1024**3)
    kv = _kv_cache_gb(params_b, context_tokens, quantization)
    return round(model_gb + kv + _FRAMEWORK_OVERHEAD_GB, 2)


def estimate_ram_gb(vram_estimate: float, has_gpu: bool) -> float:
    """Estimate host RAM needed (system RAM, not VRAM)."""
    if has_gpu:
        # With GPU: minimal host RAM needed beyond OS + process overhead
        return round(max(4.0, vram_estimate * 0.25 + 2.0), 1)
    else:
        # CPU inference: model must live in RAM
        return round(vram_estimate + 2.0, 1)


@dataclass
class ResourceEstimate:
    model_id: str
    quantization: str
    context_tokens: int
    estimated_vram_gb: float
    estimated_ram_gb: float
    estimated_disk_gb: float
    fit_level: FitLevel
    fits: bool
    recommended_context: int
    peak_vram_at_max_ctx_gb: float
    warnings: list[str] = field(default_factory=list)
    is_estimate: bool = True  # always True — only benchmarks produce measured values

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "quantization": self.quantization,
            "context_tokens": self.context_tokens,
            "estimated_vram_gb": self.estimated_vram_gb,
            "estimated_ram_gb": self.estimated_ram_gb,
            "estimated_disk_gb": self.estimated_disk_gb,
            "fit_level": self.fit_level,
            "fits": self.fits,
            "recommended_context": self.recommended_context,
            "peak_vram_at_max_ctx_gb": self.peak_vram_at_max_ctx_gb,
            "warnings": self.warnings,
            "is_estimate": self.is_estimate,
        }


def estimate_disk_gb(params_b: float, quantization: str) -> float:
    bpp = _BYTES_PER_PARAM.get(quantization, 0.5)
    # GGUF files add ~5% overhead for metadata/tokenizer
    return round(params_b * 1e9 * bpp / (1024**3) * 1.05, 2)


def _fit_level(vram_needed: float, vram_available: float) -> tuple[FitLevel, bool]:
    if vram_available <= 0:
        # CPU-only path — treat RAM as VRAM
        return "comfortable", True
    ratio = vram_needed / vram_available
    if ratio <= 0.75:
        return "comfortable", True
    if ratio <= 0.95:
        return "tight", True
    if ratio <= 1.10:
        return "not_recommended", False
    return "impossible", False


def _recommend_context(params_b: float, quantization: str, vram_gb: float) -> int:
    """Suggest a safe context length that keeps KV cache within VRAM budget."""
    bpp = _BYTES_PER_PARAM.get(quantization, 0.5)
    model_gb = params_b * 1e9 * bpp / (1024**3)
    headroom = max(0.0, vram_gb - model_gb - _FRAMEWORK_OVERHEAD_GB)
    if headroom <= 0:
        return 512
    # Estimate max context from headroom
    per_1k = _kv_cache_gb(params_b, 1000, quantization)
    max_k = headroom / per_1k if per_1k > 0 else 128
    max_tokens = int(max_k * 1000)
    # Round down to common power-of-2 context lengths
    for ctx in [131072, 65536, 32768, 16384, 8192, 4096, 2048, 1024, 512]:
        if max_tokens >= ctx:
            return ctx
    return 512


def estimate_resources(
    model_id: str,
    params_b: float,
    quantization: str,
    available_vram_gb: float,
    available_ram_gb: float,
    context_tokens: int = 4096,
) -> ResourceEstimate:
    """Compute resource estimate for a model+quantization on given hardware."""
    quant = quantization.lower()
    if quant not in _BYTES_PER_PARAM:
        quant = "q4_k"

    has_gpu = available_vram_gb > 0
    vram_needed = estimate_vram_gb(params_b, quant, context_tokens)
    ram_needed = estimate_ram_gb(vram_needed, has_gpu)
    disk_needed = estimate_disk_gb(params_b, quant)

    effective_vram = available_vram_gb if has_gpu else available_ram_gb
    fit, fits = _fit_level(vram_needed, effective_vram)

    rec_ctx = _recommend_context(params_b, quant, effective_vram)
    peak_vram = estimate_vram_gb(params_b, quant, 131072)

    warnings: list[str] = []
    warnings.append("Memory figures are estimates — actual usage varies by model implementation.")
    if fit in ("not_recommended", "impossible"):
        warnings.append(
            f"Model may not fit: needs ~{vram_needed:.1f} GB, "
            f"available ~{effective_vram:.1f} GB. Try a lower quantization."
        )
    if context_tokens > rec_ctx:
        warnings.append(
            f"Context {context_tokens} may cause OOM. Recommended max: {rec_ctx} tokens."
        )
    if peak_vram > effective_vram * 1.5:
        warnings.append(
            "Maximum context (128K+) would greatly exceed VRAM. Use shorter context."
        )

    return ResourceEstimate(
        model_id=model_id,
        quantization=quant,
        context_tokens=context_tokens,
        estimated_vram_gb=vram_needed,
        estimated_ram_gb=ram_needed,
        estimated_disk_gb=disk_needed,
        fit_level=fit,
        fits=fits,
        recommended_context=rec_ctx,
        peak_vram_at_max_ctx_gb=round(peak_vram, 2),
        warnings=warnings,
    )


def recommend_quantization(
    params_b: float,
    available_vram_gb: float,
    available_ram_gb: float,
    prefer_quality: bool = False,
) -> str:
    """Return the best quantization level that fits the available hardware."""
    effective = available_vram_gb if available_vram_gb > 0 else available_ram_gb

    # Try from highest quality to lowest
    candidates = (
        ["fp16", "q8", "q6_k", "q5_k", "q4_k", "q3_k", "q2_k"]
        if prefer_quality
        else ["q4_k", "q5_k", "q8", "q6_k", "q3_k", "q2_k"]
    )

    for quant in candidates:
        vram_needed = estimate_vram_gb(params_b, quant, 4096)
        _, fits = _fit_level(vram_needed, effective)
        if fits:
            return quant

    return "q2_k"  # last resort
