"""OpenAI language model provider.

Optional extra: ``pip install '.[openai]'``. Imported lazily by
:func:`symborg_engine.providers.resolve_language_model`, so the core never depends on it.

Written against the Responses API, which is the current primary endpoint; Chat
Completions remains supported but is degraded for newer models. The credential is read
from the environment and is never logged, written to disk, or placed in a prompt.
"""

from __future__ import annotations

import json
import os

from .base import Prompt, ProviderError

__all__ = ["OpenAILanguageModel", "DEFAULT_MODEL"]

DEFAULT_MODEL = "gpt-5.4-nano"
"""Chosen by measurement, not by tier name — see ``bench/latency.py``.

Candidate generation is short, structured and latency-sensitive, and here latency is
something the user feels: a correct sentence arriving after the conversation has moved
on has failed. Measured on this task, nano is the fastest option at standard price and
its candidate quality holds. Override with SYMBORG_LLM_MODEL."""

_MIN_OUTPUT_TOKENS = 16
"""The API's documented minimum for max_output_tokens; a smaller value is rejected."""


class OpenAILanguageModel:
    """Adapts the OpenAI SDK to the :class:`LanguageModel` protocol."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 timeout_s: float = 8.0, max_retries: int = 1,
                 fast: bool | None = None) -> None:
        """
        Args:
            timeout_s: Total budget per attempt. The SDK default is ten minutes, which
                in a live conversational product is a hang rather than an error.
            max_retries: Kept low deliberately — the SDK retries internally, so the
                worst case is roughly ``timeout_s * (max_retries + 1)``.
            fast: Opt in to the faster service tier. Off by default because it costs
                about twice as much per token, and a silent doubling of the bill is not
                a default anyone should inherit.
        """
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - exercised via resolve()
            raise ImportError(
                "The 'openai' package is required. Install with: pip install '.[openai]'"
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("no_api_key")

        self._openai = openai
        self._model = model or os.environ.get("SYMBORG_LLM_MODEL", DEFAULT_MODEL)
        self._fast = (os.environ.get("SYMBORG_LLM_FAST", "").strip().lower()
                      in {"1", "true", "yes"}) if fast is None else fast
        self._client = openai.OpenAI(api_key=key, timeout=timeout_s, max_retries=max_retries)

    def complete(self, prompt: Prompt) -> str:
        kwargs: dict = {
            "model": self._model,
            "instructions": prompt.system,
            "input": prompt.user,
            "max_output_tokens": max(_MIN_OUTPUT_TOKENS, int(prompt.max_tokens)),
            # Lowest-latency setting, and on current models the precondition for
            # temperature being accepted at all.
            "reasoning": {"effort": "none"},
            "temperature": prompt.temperature,
            # This product handles a person's own speech; retention is not a default
            # we accept on their behalf.
            "store": False,
            "stream": False,
        }
        if self._fast:
            kwargs["service_tier"] = "fast"
        if prompt.json_schema:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "symborg_reply",
                    "strict": True,
                    "schema": prompt.json_schema,
                }
            }

        response = self._call(kwargs)

        if getattr(response, "status", "completed") == "incomplete":
            details = getattr(response, "incomplete_details", None)
            raise ProviderError(f"incomplete_response: {getattr(details, 'reason', 'unknown')}")

        text = (getattr(response, "output_text", "") or "").strip()
        if not text:
            # output_text yields an empty string rather than raising when a completed
            # response carries no text part, so silence has to be caught here.
            raise ProviderError("empty_completion")

        return self._apply_stop(text, prompt.stop)

    # -- internals -------------------------------------------------------------

    def _call(self, kwargs: dict):
        """Send the request, retrying once without parameters the model rejects.

        Reasoning effort and temperature are accepted by some models and refused by
        others, and the set moves between model generations. Dropping the refused
        parameter and retrying keeps one adapter working across the family.
        """
        try:
            return self._client.responses.create(**kwargs)
        except self._openai.BadRequestError as exc:
            retry = dict(kwargs)
            message = str(exc).lower()
            for param in ("temperature", "reasoning", "service_tier"):
                if param in message:
                    retry.pop(param, None)
            if retry == kwargs:
                raise ProviderError(f"language_model_failed: {exc}") from exc
            try:
                return self._client.responses.create(**retry)
            except self._openai.OpenAIError as inner:
                raise ProviderError(f"language_model_failed: {inner}") from inner
        except self._openai.OpenAIError as exc:
            raise ProviderError(f"language_model_failed: {exc}") from exc

    @staticmethod
    def _apply_stop(text: str, stop: tuple[str, ...] | None) -> str:
        """Emulate stop sequences, which the Responses API does not provide."""
        for token in stop or ():
            index = text.find(token)
            if index != -1:
                text = text[:index]
        return text.strip()
