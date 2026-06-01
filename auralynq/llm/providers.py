"""Networked LLM providers: Ollama (local default) + OpenAI/Anthropic (optional)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx

from auralynq.llm.base import LLM
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.llm")


class OllamaLLM(LLM):
    name = "ollama"

    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _payload(self, prompt: str, system: str | None, temperature, max_tokens, stream: bool):
        return {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": stream,
            "options": {
                "temperature": temperature if temperature is not None else 0.1,
                "num_predict": max_tokens or 1024,
            },
        }

    def generate(self, prompt, *, system=None, temperature=None, max_tokens=None) -> str:
        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json=self._payload(prompt, system, temperature, max_tokens, False),
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    def stream(self, prompt, *, system=None, temperature=None, max_tokens=None) -> Iterator[str]:
        import json as _json

        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json=self._payload(prompt, system, temperature, max_tokens, True),
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = _json.loads(line)
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    break


class OpenAILLM(LLM):  # pragma: no cover - paid path
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, prompt, *, system=None, temperature=None, max_tokens=None) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=msgs,  # type: ignore[arg-type]
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=max_tokens or 1024,
        )
        return resp.choices[0].message.content or ""

    def stream(self, prompt, *, system=None, temperature=None, max_tokens=None) -> Iterator[str]:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        for chunk in self._client.chat.completions.create(
            model=self.model,
            messages=msgs,  # type: ignore[arg-type]
            stream=True,
            temperature=temperature if temperature is not None else 0.1,
        ):
            delta = chunk.choices[0].delta.content  # type: ignore[union-attr]
            if delta:
                yield delta


class AnthropicLLM(LLM):  # pragma: no cover - paid path
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, prompt, *, system=None, temperature=None, max_tokens=None) -> str:
        resp = self._client.messages.create(
            model=self.model,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=max_tokens or 1024,
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def stream(self, prompt, *, system=None, temperature=None, max_tokens=None) -> Iterator[str]:
        with self._client.messages.stream(
            model=self.model,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=max_tokens or 1024,
        ) as stream:
            yield from stream.text_stream


class CohereLLM(LLM):  # pragma: no cover - paid path
    name = "cohere"

    def __init__(self, api_key: str, model: str = "command-r-08-2024") -> None:
        import cohere

        # Cohere's v2 client exposes a Chat API with role-based messages.
        self._client = cohere.ClientV2(api_key=api_key)
        self.model = model

    def _messages(self, prompt: str, system: str | None) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def generate(self, prompt, *, system=None, temperature=None, max_tokens=None) -> str:
        resp = self._client.chat(
            model=self.model,
            messages=self._messages(prompt, system),
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=max_tokens or 1024,
        )
        # v2 returns message.content as a list of typed blocks.
        return "".join(
            block.text for block in (resp.message.content or []) if getattr(block, "text", None)
        ).strip()

    def stream(self, prompt, *, system=None, temperature=None, max_tokens=None) -> Iterator[str]:
        for event in self._client.chat_stream(
            model=self.model,
            messages=self._messages(prompt, system),
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=max_tokens or 1024,
        ):
            if event.type == "content-delta":
                delta = event.delta.message.content.text
                if delta:
                    yield delta
