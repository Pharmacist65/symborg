"""OpenAI language model provider.

Optional extra: ``pip install '.[openai]'``. Imported lazily by
:func:`symborg_engine.providers.resolve_language_model`, so the core never depends on it.

The credential is read from the environment and is never logged, never written to disk,
and never placed in a prompt.
"""

from __future__ import annotations

import os

from .base import Prompt, ProviderError

__all__ = ["OpenAILanguageModel", "DEFAULT_MODEL"]

DEFAULT_MODEL = "gpt-4o-mini"
"""A small, fast model is the right default here. Candidate generation is a short,
structured, latency-sensitive task, and in this product latency is a property the user
feels directly: a correct sentence that arrives after the conversation has moved on has
failed. Override with SYMBORG_LLM_MODEL."""


class OpenAILanguageModel:
    """Adapts the OpenAI SDK to the :class:`LanguageModel` protocol."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 timeout_s: float = 8.0) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised via resolve()
            raise ImportError(
                "The 'openai' package is required. Install with: pip install '.[openai]'"
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("no_api_key")

        self._model = model or os.environ.get("SYMBORG_LLM_MODEL", DEFAULT_MODEL)
        self._client = OpenAI(api_key=key, timeout=timeout_s)

    def complete(self, prompt: Prompt) -> str:
        """Run one non-streaming completion and return its text.

        Token-limit and temperature parameters have moved between SDK and model
        generations, and some models reject a custom temperature outright. Rather than
        pin to one shape, unsupported parameters are dropped and the call retried, so
        the adapter keeps working across model families.
        """
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        base: dict = {"model": self._model, "messages": messages}
        if prompt.stop:
            base["stop"] = list(prompt.stop)

        attempts: list[dict] = [
            {**base, "max_completion_tokens": prompt.max_tokens, "temperature": prompt.temperature},
            {**base, "max_tokens": prompt.max_tokens, "temperature": prompt.temperature},
            {**base, "max_completion_tokens": prompt.max_tokens},
            base,
        ]

        last: Exception | None = None
        for kwargs in attempts:
            try:
                response = self._client.chat.completions.create(**kwargs)
            except TypeError as exc:          # SDK rejected an argument name
                last = exc
                continue
            except Exception as exc:          # API rejected a parameter, or failed
                last = exc
                if self._is_bad_parameter(exc):
                    continue
                raise ProviderError(f"language_model_failed: {exc}") from exc

            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise ProviderError("empty_completion")
            return text

        raise ProviderError(f"language_model_failed: {last}")

    @staticmethod
    def _is_bad_parameter(exc: Exception) -> bool:
        """Whether the error is the API refusing one argument, not a real failure."""
        message = str(exc).lower()
        markers = ("unsupported_parameter", "unsupported_value", "unrecognized",
                   "not supported", "invalid_request_error", "unknown parameter")
        return any(m in message for m in markers)
