"""Hosted language model provider (Claude).

Optional extra: ``pip install '.[llm]'``. Imported lazily by
:func:`symborg_engine.providers.resolve_language_model`, so the core never depends on it.
"""

from __future__ import annotations

import os

from .base import LanguageModel, Prompt, ProviderError

__all__ = ["AnthropicLanguageModel", "DEFAULT_MODEL"]

DEFAULT_MODEL = "claude-sonnet-5"
"""Sonnet is the right default here: candidate generation is a short, structured,
latency-sensitive task, and latency is a clinical property of this product."""


class AnthropicLanguageModel:
    """Adapts the Anthropic SDK to the :class:`LanguageModel` protocol."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 timeout_s: float = 8.0) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised via resolve()
            raise ImportError(
                "The 'anthropic' package is required. Install with: pip install '.[llm]'"
            ) from exc

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("no_api_key")

        self._model = model or os.environ.get("SYMBORG_LLM_MODEL", DEFAULT_MODEL)
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout_s)

    def complete(self, prompt: Prompt) -> str:
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=prompt.max_tokens,
                temperature=prompt.temperature,
                system=prompt.system,
                messages=[{"role": "user", "content": prompt.user}],
                **({"stop_sequences": list(prompt.stop)} if prompt.stop else {}),
            )
        except Exception as exc:  # SDK raises a family of errors; the engine sees one
            raise ProviderError(f"language_model_failed: {exc}") from exc

        parts = [block.text for block in message.content if getattr(block, "type", "") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise ProviderError("empty_completion")
        return text
