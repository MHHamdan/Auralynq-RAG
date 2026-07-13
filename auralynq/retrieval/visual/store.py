"""Multi-vector (per-patch) page store with MaxSim scoring.

Each page is stored as an ``[n_patches, dim]`` matrix plus its patch-grid shape
(so a winning patch index maps back to a normalized bounding box). Scoring is
ColPali's MaxSim: for a query matrix ``Q [nq, dim]`` and a page ``P [np, dim]``,
``score = sum_i max_j Q_i · P_j``. Pure numpy; persisted per document as ``.npz``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class PageHit:
    doc_id: str
    page: int
    score: float
    patch_index: int  # best-contributing patch (for answer-region localization)
    grid_rows: int
    grid_cols: int

    def normalized_bbox(self) -> list[float]:
        """[x0, y0, x1, y1] in [0,1] for the winning patch's grid cell."""
        if self.grid_rows <= 0 or self.grid_cols <= 0:
            return [0.0, 0.0, 1.0, 1.0]
        row, col = divmod(self.patch_index, self.grid_cols)
        return [
            col / self.grid_cols,
            row / self.grid_rows,
            (col + 1) / self.grid_cols,
            (row + 1) / self.grid_rows,
        ]


class MultiVectorStore:
    """In-memory + on-disk store of per-page patch matrices."""

    def __init__(self) -> None:
        # (doc_id, page) -> (patches[n,dim], (grid_rows, grid_cols))
        self._pages: dict[tuple[str, int], tuple[np.ndarray, tuple[int, int]]] = {}

    def add_page(self, doc_id: str, page: int, patches: np.ndarray, grid: tuple[int, int]) -> None:
        self._pages[(doc_id, page)] = (np.asarray(patches, dtype=np.float32), grid)

    def __len__(self) -> int:
        return len(self._pages)

    @property
    def pages(self) -> list[tuple[str, int]]:
        return list(self._pages)

    def search(self, query: np.ndarray, k: int = 20) -> list[PageHit]:
        """Rank pages by MaxSim against the query patch matrix."""
        q = np.asarray(query, dtype=np.float32)
        if q.ndim != 2 or q.size == 0 or not self._pages:
            return []
        hits: list[PageHit] = []
        for (doc_id, page), (patches, (rows, cols)) in self._pages.items():
            if patches.size == 0:
                continue
            sim = q @ patches.T  # [nq, np]
            per_query_best = sim.max(axis=1)  # [nq]
            score = float(per_query_best.sum())
            # The patch that most often wins across query tokens localizes best.
            winners = sim.argmax(axis=1)
            patch_index = int(np.bincount(winners, minlength=patches.shape[0]).argmax())
            hits.append(PageHit(doc_id, page, score, patch_index, rows, cols))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    # ----------------------------------------------------------- persist ---
    def save(self, dir_path: Path) -> None:
        dir_path.mkdir(parents=True, exist_ok=True)
        by_doc: dict[str, list[tuple[int, np.ndarray, tuple[int, int]]]] = {}
        for (doc_id, page), (patches, grid) in self._pages.items():
            by_doc.setdefault(doc_id, []).append((page, patches, grid))
        for doc_id, entries in by_doc.items():
            arrays = {f"p{page}": patches for page, patches, _ in entries}
            meta = {str(page): list(grid) for page, _, grid in entries}
            np.savez_compressed(dir_path / f"{doc_id}.npz", **arrays)  # type: ignore[arg-type]
            (dir_path / f"{doc_id}.grid.json").write_text(json.dumps(meta), encoding="utf-8")

    @classmethod
    def load(cls, dir_path: Path) -> MultiVectorStore:
        store = cls()
        if not dir_path.exists():
            return store
        for npz in sorted(dir_path.glob("*.npz")):
            doc_id = npz.stem
            grid_path = dir_path / f"{doc_id}.grid.json"
            grids = json.loads(grid_path.read_text(encoding="utf-8")) if grid_path.exists() else {}
            with np.load(npz) as data:
                for key in data.files:
                    page = int(key[1:])  # strip the "p" prefix
                    grid = tuple(grids.get(str(page), [0, 0]))  # type: ignore[assignment]
                    store.add_page(doc_id, page, data[key], grid)  # type: ignore[arg-type]
        return store
