"""Citation attribution metrics — the numbers that make Auralynq's citations
(and visual grounding) *rigorous* rather than decorative.

Two directions of citation quality:

* **citation_precision** — of the chunks the answer cites, how many actually
  overlap the answer's content (no spurious / padded citations).
* **attribution_rate** — of the answer's claims (sentences), how many are backed
  by at least one cited chunk. Its complement is the **unsupported_claim_rate**
  (a hallucination proxy: claims asserted with no citation support).

The default scorer is deterministic (content-token overlap) so it runs in CI
with no model. Pass ``judge=...`` an ``LLM`` to upgrade support checks to an
NLI-style entailment judgement.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from auralynq.utils import tokenize

_STOP = {"the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
         "and", "or", "that", "this", "it", "as", "for", "with", "by", "at", "be"}

# A cited chunk counts as "used" if it shares at least this fraction of the
# answer's content tokens; a claim is "supported" if this fraction of *its*
# content tokens appear in some cited chunk.
CITATION_USED_TAU = 0.12
CLAIM_SUPPORT_TAU = 0.5


@dataclass
class CitationScores:
    citation_precision: float
    attribution_rate: float
    unsupported_claim_rate: float
    avg_citations: float
    n: int
    method: str = "lexical"


def _content_tokens(text: str) -> set[str]:
    return {t for t in tokenize(text or "") if t not in _STOP and len(t) > 2}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _overlap(a: set[str], b: set[str]) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def citation_scores(samples: list[dict], *, judge=None) -> CitationScores:
    """Score a list of ``{"answer": str, "citations": [{"text","source"}...]}``.

    ``judge`` (optional): an LLM whose ``.generate`` returns "yes"/"no" for a
    "does the evidence support the claim?" prompt — upgrades the lexical proxy.
    """
    if not samples:
        return CitationScores(0.0, 0.0, 0.0, 0.0, 0, "lexical")

    prec_num = prec_den = 0
    attr_num = attr_den = 0
    total_cites = 0
    method = "llm_judge" if judge is not None else "lexical"

    for s in samples:
        answer = s.get("answer", "")
        cites = s.get("citations", []) or []
        total_cites += len(cites)
        ans_tokens = _content_tokens(answer)
        cite_tokens = [_content_tokens(c.get("text", "")) for c in cites]

        # precision: each cited chunk should actually overlap the answer content
        for ct in cite_tokens:
            prec_den += 1
            if ct and _overlap(ans_tokens, ct) >= CITATION_USED_TAU:
                prec_num += 1

        # attribution: each answer claim should be supported by some citation
        for sent in _sentences(answer):
            st = _content_tokens(sent)
            if not st:
                continue
            attr_den += 1
            if _claim_supported(sent, st, cites, cite_tokens, judge):
                attr_num += 1

    n = len(samples)
    prec = prec_num / prec_den if prec_den else 0.0
    attr = attr_num / attr_den if attr_den else 0.0
    return CitationScores(
        citation_precision=round(prec, 4),
        attribution_rate=round(attr, 4),
        unsupported_claim_rate=round(1.0 - attr, 4),
        avg_citations=round(total_cites / (n or 1), 2),
        n=n,
        method=method,
    )


def _claim_supported(sent: str, sent_tokens: set[str], cites, cite_tokens, judge) -> bool:
    if judge is None:
        return any(_overlap(sent_tokens, ct) >= CLAIM_SUPPORT_TAU for ct in cite_tokens)
    # LLM-judge (NLI-style): supported if any cited chunk entails the claim.
    for c in cites:
        ev = (c.get("text") or "").strip()
        if not ev:
            continue
        prompt = (
            "Does the EVIDENCE support the CLAIM? Answer strictly 'yes' or 'no'.\n"
            f"CLAIM: {sent}\nEVIDENCE: {ev[:600]}"
        )
        try:
            verdict = judge.generate(prompt, max_tokens=3).strip().lower()
        except Exception:
            verdict = ""
        if verdict.startswith("yes"):
            return True
    return False


def to_dict(scores: CitationScores) -> dict:
    return asdict(scores)
