"""Auralynq Phase 2 research layer.

Additive, opt-in infrastructure for *research-grade* evaluation of the Auralynq
pipeline: benchmark dataset adapters, open-model (Ollama) ablation, an evidence
sufficiency controller + calibrated abstention, evaluation metrics and judges,
trace-level experiment logging, and a reproducible experiment runner.

Design rules (Phase 2 brief):
  * The production app keeps working — nothing here is imported on the hot path.
  * No fake results, no fabricated references, no secrets in artifacts.
  * No automatic large-model / large-dataset downloads (env-gated).
  * Honest abstention is preserved.

Package path note: the brief referenced ``backend/app/research``; this repo's
package is ``auralynq`` so the research layer lives at ``auralynq.research``.
"""

from __future__ import annotations

__all__ = ["__research_version__"]

__research_version__ = "0.1.0"
