"""Rolling transcript of the conversation around the person.

Bounded on purpose. Candidate quality depends on the last few turns, not on the whole
history, and an unbounded buffer would send more of someone's conversation to a provider
than the task needs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..providers.base import TranscriptChunk

__all__ = ["Transcript", "DEFAULT_WINDOW_TURNS"]

DEFAULT_WINDOW_TURNS = 8


@dataclass(slots=True)
class Transcript:
    """The recent conversation, oldest first."""

    window_turns: int = DEFAULT_WINDOW_TURNS
    _chunks: deque[TranscriptChunk] = field(
        default_factory=deque, init=False, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        # deque's maxlen is fixed at construction, so build it once the window is known.
        self._chunks = deque(maxlen=self.window_turns)

    def add(self, chunk: TranscriptChunk) -> None:
        """Record a final chunk. Interim results are ignored: acting on text that is
        still being revised produces candidates for something nobody said."""
        if chunk.is_final and chunk.text.strip():
            self._chunks.append(chunk)

    def add_text(self, text: str, speaker: str = "partner") -> None:
        self.add(TranscriptChunk(text=text, speaker=speaker))

    @property
    def chunks(self) -> list[TranscriptChunk]:
        return list(self._chunks)

    @property
    def last_partner_utterance(self) -> str:
        for chunk in reversed(self._chunks):
            if chunk.speaker != "user":
                return chunk.text
        return ""

    def is_empty(self) -> bool:
        return not self._chunks

    def render(self) -> str:
        """Format for a prompt, with speakers labelled so the model knows who is who."""
        lines = []
        for chunk in self._chunks:
            label = "Kullanıcı" if chunk.speaker == "user" else "Partner"
            lines.append(f"{label}: {chunk.text}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._chunks.clear()
