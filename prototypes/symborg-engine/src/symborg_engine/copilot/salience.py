"""Deciding whether this moment is worth saying anything at all.

Every assistant that has failed in this category failed here. Google Clips had a
dedicated ML team, custom silicon and full on-device processing, and it was
discontinued because it could not judge which moments mattered. Rabbit shipped a
hundred thousand units and kept five thousand daily users. The devices that survive
are the ones that mostly stay quiet.

So silence is not a fallback in this module — it is the structure. ``consider()``
returns silence unless every gate is passed, and the gates are ordered so that the
cheap, certain refusals happen before anything expensive is asked. Nothing here can
decide to speak; it can only fail to find a reason not to, and then hand a candidate
moment upward.

The measure is not how often it is right when it speaks. It is how often it says
nothing, and whether the few things it says were worth interrupting a person for.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "Moment", "Verdict", "Reason", "SalienceGate",
    "MIN_GAP_S", "MAX_PER_MINUTE", "DEFAULT_THRESHOLD",
]

MIN_GAP_S = 25.0
"""Shortest interval between two things said, in seconds.

A hard floor, not a preference. Something correct and well-timed still becomes
intolerable at the wrong frequency, and frequency is the failure mode users describe
when they abandon these devices."""

MAX_PER_MINUTE = 2
"""Ceiling regardless of how interesting the world gets."""

DEFAULT_THRESHOLD = 0.72
"""How good a reason has to be. Set high on purpose: the cost of speaking when it was
not worth it is measured in trust, and trust does not recover at the same rate."""


class Reason(str, Enum):
    """Why nothing was said. Every silence is explainable."""

    NOTHING_NOTABLE = "nothing_notable"
    USER_SPEAKING = "user_speaking"
    PARTNER_MID_TURN = "partner_mid_turn"
    TOO_SOON = "too_soon"
    RATE_LIMIT = "rate_limit"
    LOW_CONFIDENCE = "low_confidence"
    MUTED = "muted"
    ALREADY_KNOWN = "already_known"
    SENSITIVE_MOMENT = "sensitive_moment"


@dataclass(slots=True, frozen=True)
class Moment:
    """What is true right now."""

    transcript: str = ""
    """What has been heard of the current turn."""
    user_speaking: bool = False
    partner_mid_turn: bool = True
    """Whether the other person is still talking. Interrupting mid-sentence is the
    single most reliable way to be switched off."""
    user_asked: bool = False
    """The person addressed the system directly. This is the one case where speaking
    is the default rather than the exception."""
    sensitive: bool = False
    """A moment where the right output is nothing, whatever the system knows."""
    muted: bool = False
    at_s: float = field(default_factory=time.monotonic)


@dataclass(slots=True, frozen=True)
class Verdict:
    """The decision, and why."""

    speak: bool
    reason: Reason | None = None
    score: float = 0.0

    @classmethod
    def silent(cls, reason: Reason, score: float = 0.0) -> "Verdict":
        return cls(speak=False, reason=reason, score=score)

    @classmethod
    def worth_it(cls, score: float) -> "Verdict":
        return cls(speak=True, reason=None, score=score)

    def to_dict(self) -> dict:
        return {"speak": self.speak,
                "reason": self.reason.value if self.reason else None,
                "score": round(self.score, 3)}


@dataclass(slots=True)
class SalienceGate:
    """Holds the line between a companion and a nuisance.

        gate = SalienceGate()
        verdict = gate.consider(moment, score=0.8)
        if verdict.speak:
            gate.spoke()
    """

    threshold: float = DEFAULT_THRESHOLD
    min_gap_s: float = MIN_GAP_S
    max_per_minute: int = MAX_PER_MINUTE
    _spoken_at: list[float] = field(default_factory=list, init=False, repr=False)

    def consider(self, moment: Moment, score: float = 0.0) -> Verdict:
        """Decide whether anything should be said.

        Args:
            moment: The state of the room.
            score: How much this is worth saying, in ``[0, 1]``. Supplied by whatever
                judged the content; this class judges the timing.

        Returns:
            A verdict that is silent unless every gate passes.
        """
        if moment.muted:
            return Verdict.silent(Reason.MUTED, score)
        if moment.sensitive:
            return Verdict.silent(Reason.SENSITIVE_MOMENT, score)

        # Being addressed suspends the timing gates but not the content one: a direct
        # question deserves an answer now, and still deserves silence if there is
        # nothing worth saying.
        if moment.user_asked:
            if score <= 0.0:
                return Verdict.silent(Reason.NOTHING_NOTABLE, score)
            return Verdict.worth_it(score)

        if moment.user_speaking:
            return Verdict.silent(Reason.USER_SPEAKING, score)
        if moment.partner_mid_turn:
            return Verdict.silent(Reason.PARTNER_MID_TURN, score)

        elapsed = moment.at_s - self._spoken_at[-1] if self._spoken_at else None
        if elapsed is not None and elapsed < self.min_gap_s:
            return Verdict.silent(Reason.TOO_SOON, score)
        if self._recent(moment.at_s) >= self.max_per_minute:
            return Verdict.silent(Reason.RATE_LIMIT, score)

        if score < self.threshold:
            return Verdict.silent(Reason.LOW_CONFIDENCE, score)

        return Verdict.worth_it(score)

    def spoke(self, at_s: float | None = None) -> None:
        """Record that something was said. Not called automatically: the gate should
        not assume its verdict was acted on."""
        now = time.monotonic() if at_s is None else at_s
        self._spoken_at.append(now)
        self._spoken_at = [t for t in self._spoken_at if now - t <= 60.0]

    def _recent(self, now: float) -> int:
        return sum(1 for t in self._spoken_at if now - t <= 60.0)

    def reset(self) -> None:
        self._spoken_at.clear()
