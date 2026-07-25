"""Resilient LLM wrapper.

Wraps a primary (commercial/networked) LLM and transparently degrades down a
chain of backups if the primary raises at request time — e.g. an expired key,
inactive billing (429), rate limit, model-not-found, or a network blip.

The chain is ``primary → *backups → ExtractiveLLM``. The terminal
:class:`ExtractiveLLM` is always present and never fails, so the grounded answer
path cannot 500 (ADR-0003). Intermediate backups let a hosted provider degrade to
a *generative* local model (e.g. HF Inference Providers → local Ollama) instead of
dropping straight to quotation-only output; extractive stays the last resort.

Backups are supplied as zero-arg factories so an unreachable daemon costs nothing
until a failure actually occurs, and a backup that fails to construct is skipped
like any other failing link. The provider actually used is surfaced via
``last_fallback`` (exception type of the first failure) and ``served_by``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from auralynq.llm.base import LLM, Context
from auralynq.llm.fallback import ExtractiveLLM
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.llm.resilient")


class ResilientLLM(LLM):
    def __init__(
        self,
        primary: LLM,
        backups: list[Callable[[], LLM]] | None = None,
    ) -> None:
        self.primary = primary
        self._backups = backups or []
        self._fallback = ExtractiveLLM()
        self.name = primary.name
        self.last_fallback: str | None = None
        self.served_by: str = primary.name

    def _run(self, op: str, call):
        """Try primary, then each backup, then extractive. ``call(llm)`` does the work."""
        self.last_fallback = None
        self.served_by = self.primary.name
        try:
            return call(self.primary)
        except Exception as exc:
            self.last_fallback = type(exc).__name__
            failed_from = self.primary.name
            err = str(exc)[:200]

        for make_backup in self._backups:
            try:
                backup = make_backup()
            except Exception as exc:  # backup unavailable (daemon down, sdk missing)
                _log.warning("llm.backup_unavailable", op=op, error=str(exc)[:200])
                continue
            try:
                result = call(backup)
            except Exception as exc:
                _log.warning("llm.backup_failed", op=op, provider=backup.name, error=str(exc)[:200])
                continue
            self.served_by = backup.name
            _log.warning(
                "llm.runtime_fallback", op=op, provider=failed_from, to=backup.name, error=err
            )
            return result

        self.served_by = self._fallback.name
        _log.warning("llm.runtime_fallback_extractive", op=op, provider=failed_from, error=err)
        return call(self._fallback)

    def generate(self, prompt, *, system=None, temperature=None, max_tokens=None) -> str:
        def _call(llm: LLM) -> str:
            if llm is self._fallback:
                return llm.generate(prompt)
            return llm.generate(
                prompt, system=system, temperature=temperature, max_tokens=max_tokens
            )

        return self._run("generate", _call)

    def answer(self, question: str, contexts: list[Context], **kw) -> str:
        def _call(llm: LLM) -> str:
            if llm is self._fallback:
                return llm.answer(question, contexts)
            return llm.answer(question, contexts, **kw)

        return self._run("answer", _call)

    def stream_answer(self, question: str, contexts: list[Context], **kw) -> Iterator[str]:
        # Buffer each attempt so a mid-stream failure can cleanly switch to the
        # next link without emitting a half-answer.
        def _call(llm: LLM) -> list[str]:
            if llm is self._fallback:
                return list(llm.stream_answer(question, contexts))
            return list(llm.stream_answer(question, contexts, **kw))

        yield from self._run("stream_answer", _call)
