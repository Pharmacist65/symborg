"""Candidate utterances offered to the person, and the record of what was offered.

A candidate is a complete, speakable sentence in the person's own voice — not a cue
and not a summary. The distinction matters: the assistive path exists so that someone
can say a whole thing with one action instead of spelling it out.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal

__all__ = ["Candidate", "CandidateKind", "Offer", "MAX_CANDIDATE_WORDS"]

CandidateKind = Literal["reply", "need", "question", "repair", "social"]

MAX_CANDIDATE_WORDS = 22
"""Upper bound on candidate length. Candidates are read under conversational time
pressure, so a long one is worse than no candidate at all."""


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True, frozen=True)
class Candidate:
    """One utterance the person may choose to say.

    Immutable by design: a candidate that could change between being offered and being
    selected would break the authorship guarantee, since the authorisation is bound to
    the text that was actually shown.
    """

    text: str
    kind: CandidateKind = "reply"
    confidence: float = 0.5
    rationale: str = ""
    candidate_id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        # frozen dataclass: normalise through object.__setattr__
        object.__setattr__(self, "text", " ".join(self.text.split()))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def is_too_long(self) -> bool:
        return self.word_count > MAX_CANDIDATE_WORDS

    def to_dict(self) -> dict:
        data = asdict(self)
        data["word_count"] = self.word_count
        return data


@dataclass(slots=True)
class Offer:
    """The exact set of candidates presented at one moment.

    Kept so that a later selection can be checked against what was genuinely on screen.
    Selecting something that was never offered is a bug or an attack, and either way it
    must not produce speech.
    """

    candidates: tuple[Candidate, ...]
    offer_id: str = field(default_factory=_new_id)
    created_at_ms: int = field(default_factory=_now_ms)
    consumed: bool = False

    def __len__(self) -> int:
        return len(self.candidates)

    def get(self, index: int) -> Candidate | None:
        if 0 <= index < len(self.candidates):
            return self.candidates[index]
        return None

    def to_dict(self) -> dict:
        return {
            "offer_id": self.offer_id,
            "created_at_ms": self.created_at_ms,
            "consumed": self.consumed,
            "candidates": [c.to_dict() for c in self.candidates],
        }
