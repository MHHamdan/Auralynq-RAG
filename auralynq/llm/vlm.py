"""Vision-Language Models (VLM) for document/page image Q&A.

Powerful hosted VLMs via **Hugging Face Inference Providers**. HF exposes an
OpenAI-compatible router, so a VLM call is a chat completion whose user turn
carries both text and ``image_url`` blocks (base64 ``data:`` URIs — no public
URL, no extra egress beyond the router). Model ids are HF repo ids, e.g.
``Qwen/Qwen2.5-VL-72B-Instruct``; most capable VLMs require a paid / PRO account.

Safety mirrors the text LLM factory (``llm/factory.py``): explicit-only (never
auto-selected), token required, and hard-blocked under ``air_gapped``. When the
VLM is unavailable ``get_vlm()`` returns ``None`` so callers degrade gracefully
(text-only answer) instead of failing.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from auralynq.config import get_settings
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.vlm")

# Grounded prompt tuned for page images rather than text snippets. The pages are
# labelled "Page N" in order; the model must ground claims in what is visible.
VISUAL_SYSTEM = (
    "You are Auralynq's visual research assistant. You are shown one or more "
    "document page images, labelled in order. Answer the question strictly from "
    "what is visible in those pages — text, tables, charts, diagrams and layout.\n"
    "Rules:\n"
    "1. Open with a direct, complete answer.\n"
    "2. Cite the page you used inline as (Page N) for every factual claim.\n"
    "3. Read values off charts/tables faithfully; never guess hidden numbers.\n"
    "4. If the pages do not contain enough to answer, say exactly: "
    "'The provided pages do not contain enough information to answer this.'\n"
    "5. Never invent facts beyond what the images show."
)


def encode_image(path: Path) -> str:
    """Encode an image file as an OpenAI-style ``data:`` URI (base64)."""
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


class HuggingFaceVLM:  # pragma: no cover - paid path
    """Hosted VLM via the HF Inference Providers OpenAI-compatible router."""

    name = "huggingface-vlm"
    ROUTER_URL = "https://router.huggingface.co/v1"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=self.ROUTER_URL)
        self.model = model

    def answer(
        self,
        question: str,
        image_paths: list[Path],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        content: list[dict] = [{"type": "text", "text": question}]
        for i, p in enumerate(image_paths, start=1):
            content.append({"type": "text", "text": f"Page {i}:"})
            content.append(
                {"type": "image_url", "image_url": {"url": encode_image(p)}}
            )
        messages = [
            {"role": "system", "content": system or VISUAL_SYSTEM},
            {"role": "user", "content": content},
        ]
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=max_tokens or 1024,
        )
        return resp.choices[0].message.content or ""


def get_vlm() -> HuggingFaceVLM | None:
    """Construct the configured VLM, or ``None`` when unavailable.

    Returns ``None`` (never raises) when the VLM is disabled, air-gapped, the HF
    token is missing, or the ``openai`` SDK is not installed — so callers can fall
    back to a text-only answer.
    """
    import importlib.util

    s = get_settings()
    if not s.visual.vlm_enabled:
        return None
    if s.air_gapped:
        _log.warning("vlm.air_gapped_block", action="disabled")
        return None
    if not s.huggingface_token:
        _log.warning("vlm.no_token", action="disabled")
        return None
    if importlib.util.find_spec("openai") is None:
        _log.warning("vlm.openai_sdk_missing", action="disabled")
        return None
    try:
        return HuggingFaceVLM(s.huggingface_token, s.visual.vlm_model)
    except Exception as exc:  # pragma: no cover - construction failure
        _log.warning("vlm.init_failed", error=str(exc))
        return None
