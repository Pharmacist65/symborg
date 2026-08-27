"""Providers: protocols plus the offline defaults.

Real providers are optional extras, resolved lazily by :func:`resolve_language_model`,
so importing this package never requires any of them to be installed. Which vendor
supplies the model is a configuration choice; no engine code depends on it.

Configuration:
    SYMBORG_LLM_PROVIDER   offline | anthropic | openai   (optional; auto-detect if unset)
    SYMBORG_LLM_MODEL      model id override              (optional)
    ANTHROPIC_API_KEY / OPENAI_API_KEY

With no key set the engine runs on the offline provider. That is a supported state, not
a degraded one: it keeps tests hermetic and lets anyone run the demo immediately.
"""

from __future__ import annotations

import os
import warnings

from .base import (
    LanguageModel, Prompt, ProviderError, Synthesiser, Transcriber,
    TranscriptChunk, Utterance, VoiceRef,
)
from .offline import OfflineLanguageModel, OfflineSynthesiser, OfflineTranscriber

__all__ = [
    "LanguageModel", "Prompt", "ProviderError", "Synthesiser", "Transcriber",
    "TranscriptChunk", "Utterance", "VoiceRef",
    "OfflineLanguageModel", "OfflineSynthesiser", "OfflineTranscriber",
    "resolve_language_model", "available_providers",
]

_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
_ORDER = ("anthropic", "openai")
"""Auto-detect order when several keys are present. Arbitrary but documented and
deterministic — set SYMBORG_LLM_PROVIDER to be explicit."""


def available_providers() -> list[str]:
    """Hosted providers whose key is present in the environment."""
    return [name for name in _ORDER if os.environ.get(_KEYS[name])]


def _load(name: str) -> LanguageModel:
    if name == "anthropic":
        from .anthropic_llm import AnthropicLanguageModel
        return AnthropicLanguageModel()
    if name == "openai":
        from .openai_llm import OpenAILanguageModel
        return OpenAILanguageModel()
    raise ProviderError(f"unknown_provider: {name}")


def resolve_language_model(explicit: LanguageModel | None = None) -> LanguageModel:
    """Return the language model to use.

    Order: a provider passed in directly, then SYMBORG_LLM_PROVIDER, then whichever
    hosted key is present, then the offline default. A missing key or a missing
    optional dependency degrades with a warning — it never raises, and it never
    quietly sends data anywhere.
    """
    if explicit is not None:
        return explicit

    requested = os.environ.get("SYMBORG_LLM_PROVIDER", "").strip().lower()
    if requested == "offline":
        return OfflineLanguageModel()

    if requested:
        if requested not in _KEYS:
            warnings.warn(
                f"SYMBORG_LLM_PROVIDER={requested!r} is not recognised "
                f"(expected one of: offline, {', '.join(_ORDER)}); using the offline provider.",
                RuntimeWarning, stacklevel=2,
            )
            return OfflineLanguageModel()
        if not os.environ.get(_KEYS[requested]):
            warnings.warn(
                f"SYMBORG_LLM_PROVIDER={requested!r} but {_KEYS[requested]} is not set; "
                "using the offline provider.",
                RuntimeWarning, stacklevel=2,
            )
            return OfflineLanguageModel()
        candidates = [requested]
    else:
        candidates = available_providers()

    for name in candidates:
        try:
            return _load(name)
        except ImportError:
            warnings.warn(
                f"{_KEYS[name]} is set but the '{name}' package is not installed; "
                f"install with: pip install '.[{name}]'",
                RuntimeWarning, stacklevel=2,
            )
        except ProviderError as exc:
            warnings.warn(f"provider {name!r} unavailable ({exc}); continuing.",
                          RuntimeWarning, stacklevel=2)

    return OfflineLanguageModel()
