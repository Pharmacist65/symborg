"""Providers: protocols plus the offline defaults.

Real providers (Whisper, a hosted language model, a speech synthesiser) are optional
extras and are resolved lazily by :func:`resolve`, so importing this package never
requires them to be installed.
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
    "resolve_language_model",
]


def resolve_language_model(explicit: LanguageModel | None = None) -> LanguageModel:
    """Return the language model to use.

    Order: an explicitly supplied provider, then a configured hosted provider, then the
    offline default. A missing key is a normal, expected state — it degrades with a
    warning rather than failing, and never quietly sends data anywhere.
    """
    if explicit is not None:
        return explicit

    if os.environ.get("SYMBORG_LLM_PROVIDER", "").strip().lower() == "offline":
        return OfflineLanguageModel()

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from .anthropic_llm import AnthropicLanguageModel
        except ImportError:  # optional extra not installed
            warnings.warn(
                "ANTHROPIC_API_KEY is set but the 'anthropic' package is not installed; "
                "falling back to the offline provider. Install with: pip install '.[llm]'",
                RuntimeWarning, stacklevel=2,
            )
            return OfflineLanguageModel()
        return AnthropicLanguageModel()

    return OfflineLanguageModel()
