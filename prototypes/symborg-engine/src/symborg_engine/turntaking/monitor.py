"""Turn monitoring: deciding when to start generating.

The measured problem this exists to solve: a hosted model needs roughly 1.2–2.2 seconds
to produce candidates, and a person expects a reply about 200 ms after they stop
talking. Answering faster does not close that gap — nothing available closes it.

Starting earlier does. If the system can tell that the other person is about to finish,
it can generate during their last words, and the candidates are waiting when the turn
actually arrives. The latency does not shrink; it hides behind the end of their
sentence.

That makes turn-end prediction the load-bearing component of the product rather than an
optimisation, which is why it lives in its own module with its own measurements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .turkish import completion_score

__all__ = [
    "TurnMonitor", "TurnPredictor", "TurkishHeuristicPredictor",
    "SilencePredictor", "TurnSignal", "DEFAULT_THRESHOLD",
]

DEFAULT_THRESHOLD = 0.6
"""Where to commit to generating.

Set from the cost asymmetry, not from accuracy. Firing early and being wrong costs one
discarded generation; firing late costs the turn. So the threshold sits lower than a
balanced-accuracy optimum would put it."""


@runtime_checkable
class TurnPredictor(Protocol):
    """Estimates whether the current turn is about to end."""

    def probability(self, partial: str) -> float: ...


class TurkishHeuristicPredictor:
    """Reads Turkish verb-final morphology. No model, no network, no latency.

    The baseline any learned predictor has to beat, and useful in its own right: it
    costs nothing and it runs on a device.
    """

    def probability(self, partial: str) -> float:
        return completion_score(partial)


class SilencePredictor:
    """Waits for a pause. What every system does today, kept as the control.

    It cannot anticipate by construction — silence is only observable after the turn
    has already ended — so its lead time is zero or negative. It exists to make that
    concrete rather than assumed.
    """

    def __init__(self, silence_ms: int = 500) -> None:
        self.silence_ms = silence_ms

    def probability(self, partial: str) -> float:
        return 0.0


@dataclass(slots=True, frozen=True)
class TurnSignal:
    """The moment the monitor decided the turn was ending."""

    fired: bool
    probability: float
    partial: str
    at_ms: int
    words_heard: int

    def to_dict(self) -> dict:
        return {"fired": self.fired, "probability": round(self.probability, 3),
                "partial": self.partial, "at_ms": self.at_ms,
                "words_heard": self.words_heard}


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True)
class TurnMonitor:
    """Watches a turn unfold and fires once, when it looks about to end.

    Fires at most once per turn: a second trigger would start a second generation for
    the same turn, and the first one is already in flight.

        monitor = TurnMonitor()
        for chunk in incoming:
            if monitor.observe(chunk).fired:
                start_generating()      # while they are still speaking
        monitor.reset()                 # when the turn actually ends
    """

    predictor: TurnPredictor = field(default_factory=TurkishHeuristicPredictor)
    threshold: float = DEFAULT_THRESHOLD
    _partial: str = field(default="", init=False, repr=False)
    _fired: bool = field(default=False, init=False, repr=False)
    _started_ms: int = field(default=0, init=False, repr=False)

    def observe(self, text: str, cumulative: bool = False) -> TurnSignal:
        """Add what has just been heard and re-evaluate.

        Args:
            text: The next fragment of the current turn, or — when ``cumulative`` is
                set — everything heard of it so far.
            cumulative: Whether ``text`` replaces the running partial rather than
                extending it. Sources that already assemble the transcript set this,
                which avoids having to guess where word boundaries fall in a stream
                that may split mid-word.
        """
        if self._started_ms == 0:
            self._started_ms = _now_ms()
        self._partial = text.strip() if cumulative else f"{self._partial} {text}".strip()

        probability = float(self.predictor.probability(self._partial))
        fire = not self._fired and probability >= self.threshold
        if fire:
            self._fired = True

        return TurnSignal(
            fired=fire,
            probability=probability,
            partial=self._partial,
            at_ms=_now_ms() - self._started_ms,
            words_heard=len(self._partial.split()),
        )

    @property
    def partial(self) -> str:
        return self._partial

    @property
    def has_fired(self) -> bool:
        return self._fired

    def reset(self) -> None:
        """Clear state for the next turn."""
        self._partial = ""
        self._fired = False
        self._started_ms = 0
