"""Open-model (Ollama) profiles for the C4 local-first ablation."""

from __future__ import annotations

from auralynq.research.models.ollama_profiles import (
    PROFILES,
    ModelSpec,
    OllamaInventory,
    inventory,
    list_models_report,
    pull_commands,
)

__all__ = [
    "PROFILES",
    "ModelSpec",
    "OllamaInventory",
    "inventory",
    "list_models_report",
    "pull_commands",
]
