"""Patch embedders for visual retrieval.

``PatchEmbedder`` embeds a page image into ``[n_patches, dim]`` (with its grid
shape) and a query string into ``[n_tokens, dim]`` in the same space, so the
store can MaxSim them. The GPU ColPali model lives in ``colpali_embedder`` behind
the optional ``colpali`` extra; :class:`HashPatchEmbedder` is a deterministic,
offline ($0) fallback so the whole path stays functional and testable without a
GPU — the same philosophy as the hash text-embedder and extractive LLM.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from auralynq.telemetry import get_logger
from auralynq.utils import tokenize

_log = get_logger("auralynq.visual.embedder")
_DIM = 32


class PatchEmbedder(Protocol):
    name: str

    def embed_image(
        self, path: Path, grid: int | None = None
    ) -> tuple[np.ndarray, tuple[int, int]]: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _unit_vec(seed: str, dim: int) -> np.ndarray:
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    v = np.random.RandomState(h).standard_normal(dim).astype(np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n else v


class HashPatchEmbedder:
    """Deterministic, offline patch embedder (no torch, no model download).

    Not semantically meaningful — it exists so the late-interaction plumbing
    (indexing, MaxSim ranking, patch→bbox localization) runs and is testable at
    $0. Install the ``colpali`` extra for real visual relevance.
    """

    name = "hash-visual"

    def __init__(self, dim: int = _DIM, grid: int = 16) -> None:
        self.dim = dim
        self.grid = grid

    def embed_image(
        self, path: Path, grid: int | None = None
    ) -> tuple[np.ndarray, tuple[int, int]]:
        g = grid or self.grid
        from PIL import Image

        img = Image.open(path).convert("L").resize((g, g))
        arr = np.asarray(img, dtype=np.float32) / 255.0  # [g, g] cell intensities
        patches = np.empty((g * g, self.dim), dtype=np.float32)
        for r in range(g):
            for c in range(g):
                intensity = round(float(arr[r, c]), 2)
                patches[r * g + c] = _unit_vec(f"patch:{r}:{c}:{intensity}", self.dim)
        return patches, (g, g)

    def embed_query(self, text: str) -> np.ndarray:
        toks = [t for t in tokenize(text or "") if len(t) > 1] or [text or "q"]
        return np.stack([_unit_vec(f"tok:{t}", self.dim) for t in toks])


def get_visual_embedder(settings: Any | None = None) -> PatchEmbedder:
    """Return the configured patch embedder: ColPali when the extra is installed
    and selected, else the deterministic offline fallback."""
    from auralynq.config.settings import get_settings

    s = settings or get_settings()
    v = s.visual
    if v.visual_retrieval_provider == "colpali":
        try:
            from auralynq.retrieval.visual.colpali_embedder import ColPaliEmbedder

            return ColPaliEmbedder(model=v.visual_model, device=v.visual_device)
        except Exception as exc:  # pragma: no cover - exercised only without the extra
            _log.warning("visual.colpali_unavailable", error=str(exc), fallback="hash")
    return HashPatchEmbedder(grid=v.visual_patch_grid)
