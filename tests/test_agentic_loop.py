"""Agentic multi-hop loop — decomposition, sufficiency judging, and end-to-end
multi-hop retrieval on the offline stack (hash embedder + memory store)."""

from __future__ import annotations

from auralynq.agent.agentic import _decompose, _judge_sufficiency
from auralynq.ingest.models import Chunk, Document, SourceType
from auralynq.llm.fallback import ExtractiveLLM


class _LLM(ExtractiveLLM):
    """ExtractiveLLM (keeps .answer for synthesis) with a scripted .generate."""

    name = "scripted"

    def __init__(self, script):
        super().__init__()
        self._script = script
        self.prompts = []

    def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        for needle, reply in self._script:
            if needle in prompt:
                return reply(self) if callable(reply) else reply
        return super().generate(prompt, **kw)


# ── unit: decomposition ─────────────────────────────────────────────────────


def test_decompose_parses_sub_questions():
    llm = _LLM([("Break the QUESTION", "Who is X?\nWhat did X create?")])
    subs = _decompose(llm, "What did the founder of X create?", 4)
    assert subs == ["Who is X?", "What did X create?"]


def test_decompose_falls_back_to_original_on_junk():
    llm = _LLM([("Break the QUESTION", "")])  # empty → fallback
    assert _decompose(llm, "simple question", 4) == ["simple question"]
    llm2 = _LLM([("Break the QUESTION", lambda s: (_ for _ in ()).throw(RuntimeError()))])
    assert _decompose(llm2, "q", 4) == ["q"]


# ── unit: sufficiency ───────────────────────────────────────────────────────


class _State:
    def __init__(self, contexts):
        self.contexts = contexts


class _Ctx:
    def __init__(self, text):
        self.chunk = type("C", (), {"text": text})()


def test_judge_sufficiency():
    llm = _LLM([("PASSAGES:", "SUFFICIENT")])
    st = _State([_Ctx("some evidence")])
    assert _judge_sufficiency(llm, "q", st) is None  # sufficient → stop
    llm2 = _LLM([("PASSAGES:", "who founded Nokia")])
    assert _judge_sufficiency(llm2, "q", st) == "who founded Nokia"  # follow-up
    # no contexts → nothing to judge
    assert _judge_sufficiency(llm2, "q", _State([])) is None


# ── integration: multi-hop retrieval ────────────────────────────────────────


def _seed_two_hop_corpus():
    from auralynq.pipeline import index_documents

    docs = [
        Document(
            id="d1",
            source="a.txt",
            source_type=SourceType.text,
            title="a",
            content_hash="h1",
            chunks=[
                Chunk(
                    id=Chunk.make_id("d1", 0),
                    doc_id="d1",
                    ordinal=0,
                    source="a.txt",
                    text="Ericsson's main competitor in mobile network equipment is Nokia.",
                )
            ],
        ),
        Document(
            id="d2",
            source="b.txt",
            source_type=SourceType.text,
            title="b",
            content_hash="h2",
            chunks=[
                Chunk(
                    id=Chunk.make_id("d2", 0),
                    doc_id="d2",
                    ordinal=0,
                    source="b.txt",
                    text="Nokia was founded by Fredrik Idestam in 1865 as a pulp mill company.",
                )
            ],
        ),
    ]
    index_documents(docs)


def _run_state(monkeypatch, llm, question):
    """Drive the agentic executor and return the final AgentState (so we can
    inspect hops + accumulated contexts directly)."""
    monkeypatch.setattr("auralynq.agent.runner.get_llm", lambda: llm)
    from auralynq.agent.graph import run_agent
    from auralynq.agent.runner import _build_deps, _new_state
    from auralynq.telemetry.tracing import Trace

    deps = _build_deps(Trace(trace_id="t"), None)
    state = _new_state(question, None, agentic=True)
    return run_agent(state, deps)


def _sources(state):
    return {c.chunk.source for c in state.contexts}


def test_multihop_decomposition_retrieves_both_docs(monkeypatch):
    _seed_two_hop_corpus()
    # decompose into two hops (one per document); then judge sufficiency → stop
    llm = _LLM(
        [
            ("Break the QUESTION", "Ericsson main competitor\nwho founded Nokia pulp mill"),
            ("PASSAGES:", "SUFFICIENT"),
        ]
    )
    state = _run_state(
        monkeypatch, llm, "What did the founder of Ericsson's main competitor create?"
    )
    assert state.sub_questions == ["Ericsson main competitor", "who founded Nokia pulp mill"]
    assert state.hops >= 2
    assert state.answer.strip()
    # multi-hop ACCUMULATED evidence from BOTH documents (the whole point)
    srcs = _sources(state)
    assert any("a.txt" in s for s in srcs) and any("b.txt" in s for s in srcs)


def test_followup_hop_from_sufficiency_judge(monkeypatch):
    _seed_two_hop_corpus()
    calls = {"n": 0}

    def sufficiency(_s):
        calls["n"] += 1
        return "who founded Nokia pulp mill" if calls["n"] == 1 else "SUFFICIENT"

    # single sub-question (echo) + a follow-up produced by the sufficiency judge
    llm = _LLM(
        [("Break the QUESTION", "Ericsson main competitor Nokia"), ("PASSAGES:", sufficiency)]
    )
    state = _run_state(monkeypatch, llm, "Ericsson main competitor Nokia")
    assert state.hops >= 2  # original hop + one follow-up hop
    assert calls["n"] >= 1
    # the follow-up hop pulled in the second document's evidence
    assert any("b.txt" in s for s in _sources(state))


def test_agentic_strategy_registered():
    from auralynq.rag.strategy_registry import get_registry

    reg = get_registry()
    strat = reg.get("agentic")
    assert strat is not None
    available, _ = strat.is_available()
    assert available is True
