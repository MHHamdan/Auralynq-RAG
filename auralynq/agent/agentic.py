"""Agentic retrieve-then-reason loop (Self-RAG / IRCoT style).

Unlike the default single-shot flow (retrieve → synthesize with a lexical
sufficiency critic), this executor:

1. **Decomposes** a complex question into sub-questions with the LLM.
2. Retrieves for each hop, **accumulating** evidence across hops (so a fact found
   in hop 1 can inform the query for hop 2 — true multi-hop).
3. After the planned sub-questions, asks the LLM to **judge sufficiency**: either
   "SUFFICIENT" or a single follow-up search query that fills the gap.
4. Loops (bounded by ``agentic_max_hops`` + the latency budget), then fuses the
   full accumulated pool once and synthesizes over it.

Every LLM step degrades gracefully: unparseable decomposition falls back to the
original question, and an undecided sufficiency judgement stops the loop rather
than spinning. On the offline extractive fallback this behaves ~single-shot.
"""

from __future__ import annotations

import re

from auralynq.agent.nodes import (
    AgentDeps,
    node_fuse,
    node_plan,
    node_retrieve,
    node_route,
    node_self_check,
    node_synthesize,
    node_validate_citations,
)
from auralynq.agent.state import AgentState
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.agentic")

_DECOMPOSE_PROMPT = (
    "Break the QUESTION into the minimal set of simpler sub-questions needed to "
    "answer it, one per line, no numbering. If it is already a single simple "
    "question, return it unchanged on one line.\n"
    "Return ONLY the sub-questions.\nQUESTION: {q}"
)

_SUFFICIENCY_PROMPT = (
    "You are deciding whether the retrieved PASSAGES are enough to fully and "
    "confidently answer the QUESTION.\n"
    "If they are enough, reply with exactly: SUFFICIENT\n"
    "If not, reply with ONE short web/corpus search query (and nothing else) that "
    "would retrieve the missing information.\n\n"
    "QUESTION: {q}\n\nPASSAGES:\n{ctx}"
)


def _clean(line: str) -> str:
    line = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", line).strip()
    # Strip a leading label the LLM may echo ("QUESTION:", "Sub-question:", "Q:").
    line = re.sub(r"^(?:sub-?question|question|query|q)\s*[:.)-]\s*", "", line, flags=re.I).strip()
    return line


def _decompose(llm, question: str, max_sub: int) -> list[str]:
    try:
        raw = llm.generate(_DECOMPOSE_PROMPT.format(q=question), max_tokens=200, temperature=0.0)
    except Exception:
        return [question]
    subs: list[str] = []
    for ln in (raw or "").splitlines():
        ln = _clean(ln)
        # keep plausible sub-questions: non-empty, not echoing the whole prompt,
        # reasonably short. Interrogative or short declarative lines qualify.
        if ln and len(ln) <= 200 and ln.lower() != "sufficient":
            subs.append(ln)
        if len(subs) >= max_sub:
            break
    # If the model didn't produce clean sub-questions, just use the question.
    if not subs or (len(subs) == 1 and subs[0].lower() == question.lower()):
        return [question]
    return subs


def _passages(state: AgentState, limit: int = 8) -> str:
    lines = []
    for i, c in enumerate(state.contexts[:limit], 1):
        lines.append(f"[{i}] {c.chunk.text[:300]}")
    return "\n".join(lines)


def _judge_sufficiency(llm, question: str, state: AgentState) -> str | None:
    """Return None when the evidence is sufficient, else a follow-up query."""
    if not state.contexts:
        return None
    try:
        out = llm.generate(
            _SUFFICIENCY_PROMPT.format(q=question, ctx=_passages(state)),
            max_tokens=40,
            temperature=0.0,
        ).strip()
    except Exception:
        return None
    if not out or "sufficient" in out.lower():
        return None
    followup = _clean(out.splitlines()[0])
    # A follow-up must be short and query-like — reject echoed passages (citation
    # markers, long text, many words), which the offline extractive LLM produces.
    if (
        not followup
        or len(followup) > 120
        or len(followup.split()) > 15
        or re.search(r"\[\d+\]", followup)
    ):
        return None
    return followup


def agentic_steps(state: AgentState, deps: AgentDeps):
    """Run decompose → multi-hop retrieval → fuse, mutating ``state`` in place
    and yielding ``step`` events for the UI. Leaves ``state.contexts`` populated;
    does NOT synthesize (the caller streams the answer). ``node_plan`` is assumed
    already done by the caller."""
    s = deps.settings
    max_hops = max(1, s.agent.agentic_max_hops)

    with deps.trace.span("agentic_decompose") as sp:
        sub_questions = _decompose(
            deps.llm, state.original_question, s.agent.agentic_max_subquestions
        )
        state.sub_questions = sub_questions
        sp.attributes.update(n_sub=len(sub_questions), sub_questions=sub_questions)
    yield {
        "type": "step",
        "phase": "decompose",
        "label": "Planning sub-questions",
        "detail": f"{len(sub_questions)} sub-question(s)",
        "sub_questions": sub_questions,
    }

    queue: list[str] = list(sub_questions)
    seen: set[str] = set()
    while state.hops < max_hops and not state.out_of_budget():
        if not queue:
            break
        q = queue.pop(0)
        key = q.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        state.question = q
        state.hops += 1
        state.iteration = state.hops
        before = len(state.contexts)
        with deps.trace.span("agentic_hop", hop=state.hops, query=q):
            state = node_route(state, deps)
            state = node_retrieve(state, deps)  # accumulates into state.contexts
        yield {
            "type": "step",
            "phase": "hop",
            "hop": state.hops,
            "label": f"Retrieving (hop {state.hops})",
            "query": q,
            "retrieved": len(state.contexts) - before,
        }

        # After exhausting the planned sub-questions, let the LLM decide whether
        # to keep going (Self-RAG sufficiency) and propose the next query.
        if not queue and state.hops < max_hops and not state.out_of_budget():
            followup = _judge_sufficiency(deps.llm, state.original_question, state)
            if followup and followup.strip().lower() not in seen:
                queue.append(followup)
                state.notes.append(f"hop {state.hops}: follow-up → {followup}")
                sufficient, detail = False, f"follow-up: {followup}"
            else:
                sufficient, detail = True, "sufficient"
            yield {
                "type": "step",
                "phase": "check",
                "label": "Assessing evidence",
                "sufficient": sufficient,
                "detail": detail,
            }

    # Fuse the full accumulated pool once; the caller synthesizes the answer.
    state.question = state.original_question
    state = node_fuse(state, deps)
    yield {"type": "step", "phase": "synthesize", "label": "Synthesizing answer"}
    _log.info(
        "agentic.loop",
        hops=state.hops,
        sub_questions=len(sub_questions),
        contexts=len(state.contexts),
    )


def run_agentic(state: AgentState, deps: AgentDeps) -> AgentState:
    """Multi-hop retrieve-then-reason executor (non-streaming). Same node
    vocabulary as the default flow, but decomposition + LLM-judged sufficiency
    drive the loop and evidence accumulates across hops."""
    state = node_plan(state, deps)
    for _ in agentic_steps(state, deps):  # drain the step generator (mutates state)
        pass
    state = node_synthesize(state, deps)
    state = node_self_check(state, deps)
    state = node_validate_citations(state, deps)
    _log.info("agentic.done", hops=state.hops, contexts=len(state.contexts))
    return state
