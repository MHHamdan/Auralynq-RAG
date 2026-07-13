"""GPU ColPali patch embedder (optional ``colpali`` extra).

Wraps ``colpali-engine`` (a ColPali / ColQwen2 model + processor). torch and the
model are imported lazily so the module is only touched when the extra is
installed and ``visual_retrieval_provider="colpali"``. GPU-favored; runs on CPU
too, slowly. Not exercised by the offline test suite (coverage-omitted).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class ColPaliEmbedder:  # pragma: no cover - requires the GPU `colpali` extra
    name = "colpali"

    def __init__(self, model: str = "vidore/colpali-v1.3", device: str = "auto") -> None:
        import torch
        from colpali_engine.models import ColPali, ColPaliProcessor

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self._torch = torch
        self.model = ColPali.from_pretrained(model, torch_dtype=torch.float32).to(device).eval()
        self.processor = ColPaliProcessor.from_pretrained(model)

    def _to_numpy(self, tensor) -> np.ndarray:
        return tensor.detach().to("cpu", dtype=self._torch.float32).numpy().astype(np.float32)

    def embed_image(
        self, path: Path, grid: int | None = None
    ) -> tuple[np.ndarray, tuple[int, int]]:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        batch = self.processor.process_images([img]).to(self.device)
        with self._torch.no_grad():
            emb = self.model(**batch)  # [1, n_patches, dim]
        patches = self._to_numpy(emb[0])
        # ColPali patch grids are square; infer side from the patch count.
        side = round(patches.shape[0] ** 0.5) or 1
        return patches, (side, side)

    def embed_query(self, text: str) -> np.ndarray:
        batch = self.processor.process_queries([text]).to(self.device)
        with self._torch.no_grad():
            emb = self.model(**batch)  # [1, n_tokens, dim]
        return self._to_numpy(emb[0])
