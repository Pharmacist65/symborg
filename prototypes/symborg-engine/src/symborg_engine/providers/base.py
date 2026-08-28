"""Provider protocols.

The engine depends on these shapes, never on a vendor. Anything that satisfies the
protocol can be dropped in without touching engine logic, and the core imports nothing
outside the standard library so that a missing optional dependency can never break an
import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "TranscriptChunk", "Prompt", "VoiceRef", "Utterance",
    "Transcriber", "LanguageModel", "Synthesiser", "ProviderError",
]


class ProviderError(RuntimeError):
    """A provider failed. Callers degrade; they do not fabricate output."""


@dataclass(slots=True, frozen=True)
class TranscriptChunk:
    """One recognised span of speech."""

    text: str
    speaker: str = "partner"
    start_ms: int = 0
    end_ms: int = 0
    is_final: bool = True


@dataclass(slots=True, frozen=True)
class Prompt:
    """A request to a language model, kept provider-neutral."""

    system: str
    user: str
    max_tokens: int = 512
    temperature: float = 0.4
    stop: tuple[str, ...] = field(default_factory=tuple)
    image: bytes | None = None
    """Optional image the question is about, as encoded bytes (PNG or JPEG).

    Providers that cannot see ignore it and answer from the text alone, which is why
    callers must write a question that still makes sense without the picture.
    """
    image_mime: str = "image/jpeg"

    json_schema: dict | None = None
    """Optional shape the reply should conform to.

    A hint, not a contract: providers that support constrained decoding use it to
    guarantee well-formed output; the rest ignore it and the caller still parses
    defensively. Keeping it optional is what lets one prompt serve every provider.
    """


@dataclass(slots=True, frozen=True)
class VoiceRef:
    """A reference to a banked voice.

    Holds an identifier, never audio: recordings of a person's voice are personal data
    and stay where the person put them.
    """

    voice_id: str
    label: str = ""
    is_own_voice: bool = False


@dataclass(slots=True, frozen=True)
class Utterance:
    """Synthesised audio plus what it says, for logging and playback."""

    text: str
    audio: bytes
    mime_type: str = "audio/wav"
    voice_id: str = ""


@runtime_checkable
class Transcriber(Protocol):
    """Turns audio into text."""

    def transcribe(self, audio: bytes) -> TranscriptChunk: ...


@runtime_checkable
class LanguageModel(Protocol):
    """Completes a prompt. Implementations must raise ProviderError, not return junk."""

    def complete(self, prompt: Prompt) -> str: ...


@runtime_checkable
class Synthesiser(Protocol):
    """Turns authorised text into audio."""

    def synthesise(self, text: str, voice: VoiceRef) -> Utterance: ...
