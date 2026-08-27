"""Driving a session from a live transcript.

The engine does not care where speech comes from. A test replays text, a desktop build
reads a local recogniser, a hosted build reads a streaming speech API — all of them
produce the same thing: fragments of a turn, arriving while the speaker is still
talking, ending when they stop.

Keeping that behind one protocol is what makes the audio layer replaceable. It is
solved engineering that belongs to whoever solved it best, and the part worth owning
sits above it: deciding, from those fragments, that the turn is about to end.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Protocol, runtime_checkable

from .session import OfferResult, Session

__all__ = ["Fragment", "TranscriptStream", "TextStream", "TurnResult", "drive"]


@dataclass(slots=True, frozen=True)
class Fragment:
    """A piece of a turn in progress."""

    text: str
    is_final: bool = False
    """True on the fragment that ends the turn — the speaker has stopped."""
    at_ms: int = 0
    """Milliseconds since the turn began, if the source reports it."""
    cumulative: bool = False
    """Whether ``text`` is the whole turn so far rather than an increment.

    Recognisers differ: some emit word-level increments, some revise and re-emit the
    running transcript, and some split mid-word. A source that has already assembled
    the partial says so here, and the monitor replaces instead of appending — which
    removes any need to guess where a space belongs."""


@runtime_checkable
class TranscriptStream(Protocol):
    """Yields fragments of speech as they are recognised."""

    def __iter__(self) -> Iterator[Fragment]: ...


@dataclass(slots=True)
class TextStream:
    """Replays written text at a chosen pace.

    For tests and for measurement: the same turn can be replayed exactly, which a
    microphone cannot do. ``gap_ms`` of zero runs it as fast as possible.
    """

    fragments: Iterable[str]
    gap_ms: int = 0

    def __iter__(self) -> Iterator[Fragment]:
        items = list(self.fragments)
        elapsed = 0
        for i, text in enumerate(items):
            last = i == len(items) - 1
            yield Fragment(text=text, is_final=last, at_ms=elapsed)
            if not last and self.gap_ms:
                time.sleep(self.gap_ms / 1000)
                elapsed += self.gap_ms


@dataclass(slots=True, frozen=True)
class TurnResult:
    """What happened across one turn."""

    partial: str
    result: OfferResult
    fired_at_ms: int | None
    turn_end_ms: int

    @property
    def lead_ms(self) -> int:
        """How long before the turn ended that generation started.

        Zero means the system waited for silence like everything else does.
        """
        if self.fired_at_ms is None:
            return 0
        return max(0, self.turn_end_ms - self.fired_at_ms)

    @property
    def anticipated(self) -> bool:
        return self.fired_at_ms is not None

    def to_dict(self) -> dict:
        return {"partial": self.partial, "lead_ms": self.lead_ms,
                "anticipated": self.anticipated, **self.result.to_dict()}


def drive(
    session: Session,
    stream: TranscriptStream,
    on_turn: Callable[[TurnResult], None] | None = None,
) -> list[TurnResult]:
    """Feed a session from a stream, one turn at a time.

    Each fragment is offered to the turn monitor, which may start generating before the
    speaker finishes. When the turn ends, candidates are presented — already waiting if
    the prediction fired in time.

    Args:
        session: The session to drive.
        stream: Where fragments come from.
        on_turn: Called as each turn completes, for live display.

    Returns:
        One :class:`TurnResult` per completed turn.
    """
    turns: list[TurnResult] = []
    fired_at: int | None = None

    for fragment in stream:
        # A blank fragment is skipped unless it closes the turn: a recogniser signals
        # the end of an utterance without necessarily carrying more text.
        if not fragment.text.strip() and not fragment.is_final:
            continue

        if fragment.text.strip():
            signal = session.hear_partial(fragment.text, cumulative=fragment.cumulative)
            if signal.fired and fired_at is None:
                fired_at = fragment.at_ms

        if fragment.is_final:
            partial = session.monitor.partial
            result = session.offer()
            turn = TurnResult(
                partial=partial, result=result,
                fired_at_ms=fired_at, turn_end_ms=fragment.at_ms,
            )
            turns.append(turn)
            if on_turn is not None:
                on_turn(turn)
            session.transcript.add_text(partial, speaker="partner")
            session.monitor.reset()
            fired_at = None

    return turns
