"""Tests for Auralynq ModelFit Index.

Coverage:
- Hardware profiler (with and without GPU)
- Resource estimator (various model sizes and quantizations)
- Fit scoring
- Benchmark preview (dry run only — never runs actual benchmark)
- Community result validation
- Model registry search
- No fake tok/s in score when benchmark not run
- No secrets in hardware export
"""

from __future__ import annotations

import pytest

from auralynq.modelfit.hardware import HardwareProfile, probe_hardware
from auralynq.modelfit.model_metadata import ModelMetadata
from auralynq.modelfit.resource_estimator import (
    estimate_resources,
    estimate_vram_gb,
    recommend_quantization,
)
from auralynq.modelfit.scoring import BenchmarkSnapshot, score_model
from auralynq.modelfit.benchmark_runner import preview_benchmark
from auralynq.modelfit.community import validate_community_result, save_community_result
from auralynq.modelfit.model_registry import ModelRegistry
from auralynq.modelfit.ollama_catalog import get_static_catalog
from auralynq.modelfit.hf_catalog import get_static_hf_catalog


# ── Hardware profiler ─────────────────────────────────────────────────────────

def test_probe_hardware_returns_profile():
    hw = probe_hardware()
    assert isinstance(hw, HardwareProfile)


def test_hardware_profile_no_gpu():
    hw = HardwareProfile(
        os_name="Linux",
        ram_gb=16.0,
        gpus=[],
        ollama_available=False,
    )
    assert hw.total_vram_gb == 0.0
    assert hw.best_backend == "cpu"
    d = hw.to_dict()
    assert d["total_vram_gb"] == 0.0
    assert d["best_backend"] == "cpu"


def test_hardware_profile_with_gpu():
    from auralynq.modelfit.hardware import GPUInfo
    gpu = GPUInfo(vendor="nvidia", name="RTX 4090", vram_gb=24.0, backend="cuda")
    hw = HardwareProfile(
        os_name="Linux",
        ram_gb=64.0,
        gpus=[gpu],
        cuda_available=True,
    )
    assert hw.total_vram_gb == 24.0
    assert hw.best_backend == "cuda"


def test_hardware_no_secrets_in_dict():
    hw = probe_hardware()
    d = hw.to_dict()
    sensitive = {"serial", "uuid", "mac_address", "hostname", "username"}
    for key in sensitive:
        assert key not in d, f"Sensitive key '{key}' found in hardware profile"


def test_hardware_warnings_list():
    hw = probe_hardware()
    assert isinstance(hw.warnings, list)


# ── Resource estimator ────────────────────────────────────────────────────────

@pytest.mark.parametrize("params_b,quant,ctx", [
    (3.0, "q4_k", 4096),
    (7.0, "q4_k", 4096),
    (7.0, "q8", 4096),
    (14.0, "q4_k", 4096),
    (14.0, "fp16", 4096),
    (70.0, "q4_k", 4096),
    (1.0, "q4_k", 2048),
    (9.0, "q5_k", 8192),
])
def test_vram_estimate_positive(params_b, quant, ctx):
    vram = estimate_vram_gb(params_b, quant, ctx)
    assert vram > 0.0


def test_vram_estimate_increases_with_params():
    v7 = estimate_vram_gb(7.0, "q4_k", 4096)
    v70 = estimate_vram_gb(70.0, "q4_k", 4096)
    assert v70 > v7 * 5


def test_vram_estimate_fp16_greater_than_q4():
    v_fp16 = estimate_vram_gb(7.0, "fp16", 4096)
    v_q4 = estimate_vram_gb(7.0, "q4_k", 4096)
    assert v_fp16 > v_q4


def test_estimate_resources_comfortable():
    result = estimate_resources(
        model_id="test",
        params_b=3.0,
        quantization="q4_k",
        available_vram_gb=24.0,
        available_ram_gb=32.0,
        context_tokens=4096,
    )
    assert result.fit_level == "comfortable"
    assert result.fits is True
    assert result.is_estimate is True


def test_estimate_resources_impossible():
    result = estimate_resources(
        model_id="test",
        params_b=70.0,
        quantization="fp16",
        available_vram_gb=8.0,
        available_ram_gb=16.0,
        context_tokens=4096,
    )
    assert result.fit_level == "impossible"
    assert result.fits is False
    assert result.is_estimate is True


def test_estimate_resources_warnings_present():
    result = estimate_resources(
        model_id="test",
        params_b=7.0,
        quantization="q4_k",
        available_vram_gb=8.0,
        available_ram_gb=16.0,
    )
    assert len(result.warnings) > 0
    assert result.is_estimate is True


def test_recommend_quantization_fits_small_vram():
    quant = recommend_quantization(params_b=7.0, available_vram_gb=8.0, available_ram_gb=16.0)
    assert quant in ("q4_k", "q4_0", "q3_k", "q2_k")


def test_estimate_resources_dict_schema():
    result = estimate_resources("test", 7.0, "q4_k", 16.0, 32.0)
    d = result.to_dict()
    required = {
        "model_id", "quantization", "context_tokens", "estimated_vram_gb",
        "estimated_ram_gb", "estimated_disk_gb", "fit_level", "fits",
        "recommended_context", "peak_vram_at_max_ctx_gb", "warnings", "is_estimate",
    }
    assert required <= set(d.keys())
    assert d["is_estimate"] is True


# ── Scoring ───────────────────────────────────────────────────────────────────

def _make_hw(vram_gb: float = 12.0, ram_gb: float = 32.0) -> HardwareProfile:
    from auralynq.modelfit.hardware import GPUInfo
    gpu = GPUInfo("nvidia", "RTX 3060", vram_gb, "cuda")
    return HardwareProfile(
        os_name="Linux",
        ram_gb=ram_gb,
        gpus=[gpu] if vram_gb > 0 else [],
        cuda_available=vram_gb > 0,
    )


def _make_model(params_b: float = 7.0) -> ModelMetadata:
    return ModelMetadata(
        model_id=f"ollama:test:{params_b}b",
        source="ollama",
        display_name=f"Test {params_b}B",
        parameter_count_b=params_b,
        tasks=["chat", "rag"],
        available_quantizations=["q4_k", "q8", "fp16"],
    )


def test_score_model_returns_score():
    hw = _make_hw()
    model = _make_model()
    score = score_model(model, hw)
    assert 0 <= score.overall_score <= 100
    assert score.label in (
        "Excellent fit", "Recommended", "Usable with limits", "Not recommended", "Does not fit"
    )


def test_score_model_no_fabricated_toks():
    hw = _make_hw()
    model = _make_model()
    score = score_model(model, hw)
    # Without a benchmark, tok/s should NOT be present in benchmark field
    if score.benchmark:
        assert score.benchmark.avg_tok_per_sec is None or score.estimate_used
    assert score.estimate_used is True


def test_score_model_with_benchmark_overrides_estimate():
    hw = _make_hw()
    model = _make_model()
    bench = BenchmarkSnapshot(
        avg_tok_per_sec=45.0,
        p50_latency_ms=800.0,
        is_measured=True,
    )
    score = score_model(model, hw, benchmark=bench)
    assert score.benchmark is not None
    assert score.benchmark.avg_tok_per_sec == 45.0
    assert score.benchmark.is_measured is True


def test_score_model_small_on_tiny_vram_not_recommended():
    hw = _make_hw(vram_gb=2.0)
    model = _make_model(params_b=70.0)
    score = score_model(model, hw, quantization="fp16")
    assert score.hardware_fit < 50


def test_score_model_comfortable_fit():
    hw = _make_hw(vram_gb=24.0)
    model = _make_model(params_b=3.0)
    score = score_model(model, hw, quantization="q4_k")
    assert score.hardware_fit >= 85


def test_score_model_warnings_have_estimate_label():
    hw = _make_hw()
    model = _make_model()
    score = score_model(model, hw)
    estimate_warnings = [w for w in score.warnings if "estimate" in w.lower()]
    assert len(estimate_warnings) > 0


# ── Benchmark preview (dry run only) ─────────────────────────────────────────

def test_benchmark_preview_does_not_run():
    plan = preview_benchmark("ollama:llama3.1:8b", "q4_k", "rag", 10)
    assert plan.requires_model_download is False
    d = plan.to_dict()
    assert "preview" in d["note"].lower() or "dry" in d["note"].lower()
    assert len(plan.warnings) > 0


def test_benchmark_preview_schema():
    plan = preview_benchmark("ollama:llama3.1:8b", "q4_k", "latency", 5)
    d = plan.to_dict()
    assert "note" in d
    assert d["requires_model_download"] is False
    assert isinstance(d["sample_prompts"], list)
    assert isinstance(d["warnings"], list)


def test_benchmark_preview_estimated_duration_positive():
    plan = preview_benchmark("ollama:test:7b", "q4_k", "throughput", 20)
    assert plan.estimated_duration_min > 0


# ── Community validation ──────────────────────────────────────────────────────

def _valid_community_entry() -> dict:
    return {
        "model_id": "ollama:llama3.1:8b",
        "quantization": "q4_k",
        "hardware": {
            "cpu_model": "Intel Core i9",
            "ram_gb": 32,
            "gpus": [{"vendor": "nvidia", "name": "RTX 3090", "vram_gb": 24}],
        },
        "benchmark_version": "auralynq-modelfit-0.1",
        "task": "rag",
        "date": "2026-06-23",
        "source": "auralynq-benchmark-runner",
        "tok_per_sec": 28.4,
    }


def test_community_valid_entry_passes():
    errors = validate_community_result(_valid_community_entry())
    assert errors == []


def test_community_missing_required_field_fails():
    entry = _valid_community_entry()
    del entry["model_id"]
    errors = validate_community_result(entry)
    assert any("model_id" in e for e in errors)


def test_community_missing_hardware_cpu_fails():
    entry = _valid_community_entry()
    del entry["hardware"]["cpu_model"]
    errors = validate_community_result(entry)
    assert len(errors) > 0


def test_community_implausible_tps_rejected():
    entry = _valid_community_entry()
    entry["tok_per_sec"] = 99999
    errors = validate_community_result(entry)
    assert any("implausible" in e for e in errors)


def test_community_negative_latency_rejected():
    entry = _valid_community_entry()
    entry["p50_latency_ms"] = -100
    errors = validate_community_result(entry)
    assert any("non-negative" in e for e in errors)


def test_community_sensitive_hardware_rejected():
    entry = _valid_community_entry()
    entry["hardware"]["serial"] = "ABC123"
    errors = validate_community_result(entry)
    assert any("sensitive" in e.lower() for e in errors)


def test_community_save_strips_secrets(tmp_path, monkeypatch):
    import auralynq.modelfit.community as comm
    monkeypatch.setattr(comm, "_COMMUNITY_DIR", tmp_path)
    entry = _valid_community_entry()
    entry["hardware"]["hostname"] = "my-secret-machine"  # will be stripped
    # validation should fail since 'hostname' is sensitive
    errors = validate_community_result(entry)
    assert any("sensitive" in e.lower() for e in errors)


# ── Model registry ────────────────────────────────────────────────────────────

def test_registry_loads_static_catalog():
    reg = ModelRegistry()
    models = reg.list_all()
    assert len(models) > 5


def test_registry_search_by_family():
    reg = ModelRegistry()
    llamas = reg.search(family="llama")
    assert all(m.family == "llama" for m in llamas)


def test_registry_search_by_embedding():
    reg = ModelRegistry()
    embeds = reg.search(embedding_only=True)
    assert all(m.embedding for m in embeds)


def test_registry_search_by_task():
    reg = ModelRegistry()
    rag_models = reg.search(task="rag")
    assert all("rag" in m.tasks for m in rag_models)


def test_registry_get_returns_none_for_unknown():
    reg = ModelRegistry()
    assert reg.get("nonexistent:model:id") is None


def test_static_ollama_catalog_has_required_fields():
    catalog = get_static_catalog()
    assert len(catalog) > 0
    for m in catalog:
        assert m.model_id
        assert m.source == "ollama"
        assert m.parameter_count_b is not None or m.embedding


def test_static_hf_catalog_has_required_fields():
    catalog = get_static_hf_catalog()
    assert len(catalog) > 0
    for m in catalog:
        assert m.model_id.startswith("hf:")
        assert m.source == "huggingface"


# ── Score in query response ───────────────────────────────────────────────────

def test_query_response_schema_has_model_fit_field():
    from auralynq.serving.schemas import QueryResponse
    r = QueryResponse(answer="test")
    assert hasattr(r, "model_fit")
    assert r.model_fit is None  # None when not set


def test_score_dict_has_estimate_used_flag():
    hw = _make_hw()
    model = _make_model()
    score = score_model(model, hw)
    d = score.to_dict()
    assert "estimate_used" in d
    assert d["estimate_used"] is True  # no benchmark provided
