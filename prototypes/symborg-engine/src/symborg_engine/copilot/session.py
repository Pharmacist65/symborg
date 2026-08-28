"""The copilot loop.

Hears the room, keeps the few things worth keeping, and almost always says nothing.

The shape is deliberately different from an assistant. An assistant is asked and
answers; this listens to a conversation it is not part of, and its normal output is
silence. Speaking is the exception, and every exception has to pass both a content
judgement and a timing gate before a single line reaches the person's ear.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..context.transcript import Transcript
from ..providers import resolve_language_model, resolve_synthesiser
from ..providers.base import LanguageModel, Synthesiser, Utterance, VoiceRef
from ..turntaking import TurnMonitor
from .extract import extract
from .judge import decide
from .memory import Memory, Recollection
from .salience import Moment, Reason, SalienceGate, Verdict

__all__ = ["Copilot", "Heard"]


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True, frozen=True)
class Heard:
    """What happened when a turn ended. Usually nothing, which is the point."""

    transcript: str
    verdict: Verdict
    # Keyword-only past this point. What reaches a person's ear should never be
    # decided by argument position; passing the wrong tuple in the third slot once
    # was enough.
    said: str = field(default="", kw_only=True)
    remembered: tuple[str, ...] = field(default=(), kw_only=True)
    utterance: Utterance | None = field(default=None, kw_only=True)
    latency_ms: int = field(default=0, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.said, str):
            raise TypeError(f"said must be a string, got {type(self.said).__name__}")

    @property
    def spoke(self) -> bool:
        return bool(self.said)

    def to_dict(self) -> dict:
        return {"transcript": self.transcript, "said": self.said,
                "remembered": list(self.remembered), "latency_ms": self.latency_ms,
                **self.verdict.to_dict()}


@dataclass(slots=True)
class Copilot:
    """Something that listens and mostly stays out of the way.

        copilot = Copilot(memory=Memory.open("~/symborg/memory.jsonl"))
        for fragment in speech:
            copilot.hear_partial(fragment)
        heard = copilot.turn_ended()
        if heard.spoke:
            play(heard.utterance)
    """

    model: LanguageModel | None = None
    synthesiser: Synthesiser | None = None
    memory: Memory = field(default_factory=Memory)
    gate: SalienceGate = field(default_factory=SalienceGate)
    monitor: TurnMonitor = field(default_factory=TurnMonitor)
    transcript: Transcript = field(default_factory=Transcript)
    voice: VoiceRef = field(default_factory=lambda: VoiceRef(voice_id="offline"))
    remember: bool = True
    muted: bool = False
    sensitive: bool = False
    """Set by the person, or by whatever knows the situation. When true nothing is
    said whatever is known — a funeral does not need a fact."""
    clock: Callable[[], float] = time.monotonic
    """Seconds, monotonic. Injectable so a day of conversation can be replayed in a
    second without reaching into the gate's private state."""

    _asked: bool = field(default=False, init=False, repr=False)
    _log: list[Heard] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.model = resolve_language_model(self.model)
        self.synthesiser = resolve_synthesiser(self.synthesiser)

    # -- listening -------------------------------------------------------------

    def hear_partial(self, text: str, cumulative: bool = False) -> None:
        """Feed a fragment of speech that is still in progress."""
        self.monitor.observe(text, cumulative=cumulative)

    def address(self) -> None:
        """The person spoke to it directly. Suspends the timing gates for this turn,
        not the judgement — being asked is not a reason to say something empty."""
        self._asked = True

    # -- the decision ----------------------------------------------------------

    def turn_ended(self, transcript: str | None = None) -> Heard:
        """A turn finished. Decide whether it deserves anything.

        Returns:
            What happened. In ordinary conversation this is silence with a reason,
            and that is the expected result rather than a failure.
        """
        started = _now_ms()
        text = (transcript if transcript is not None else self.monitor.partial).strip()
        asked, self._asked = self._asked, False
        self.monitor.reset()

        if not text:
            return self._record(Heard("", Verdict.silent(Reason.NOTHING_NOTABLE)))

        self.transcript.add_text(text, speaker="partner")

        # Judge against memory as it stood BEFORE this turn. Storing first and then
        # judging makes it hear its own echo: the sentence just spoken is "in memory",
        # so it confirms the speaker back to themselves. Nobody needs that.
        at_s = self.clock()
        moment = Moment(
            at_s=at_s,
            transcript=text,
            partner_mid_turn=False,      # the turn is over by definition here
            user_asked=asked,
            sensitive=self.sensitive,
            muted=self.muted,
        )

        # Ask the cheap gates before paying for a judgement.
        # Ask the cheap gates before paying for a judgement.
        provisional = self.gate.consider(moment, score=1.0)
        if not provisional.speak:
            return self._record(Heard(text, provisional, remembered=self._store(text),
                                      latency_ms=_now_ms() - started))

        judgement = decide(self.model, text, self.memory.render(text), asked=asked)
        verdict = self.gate.consider(moment, score=judgement.score)
        if not verdict.speak or not judgement.worth_it:
            reason = verdict.reason or Reason.NOTHING_NOTABLE
            return self._record(Heard(text, Verdict.silent(reason, judgement.score),
                                      remembered=self._store(text), latency_ms=_now_ms() - started))

        utterance = self.synthesiser.synthesise(judgement.say, self.voice)
        self.gate.spoke(at_s)
        return self._record(Heard(
            transcript=text, verdict=verdict, said=judgement.say,
            remembered=self._store(text), utterance=utterance,
            latency_ms=_now_ms() - started,
        ))

    def _store(self, text: str) -> tuple[str, ...]:
        """Keep whatever this turn was worth keeping. Runs after the decision to speak,
        never before it."""
        if not self.remember:
            return ()
        return tuple(i.text for i in extract(self.model, text) if self.memory.keep(i))

    # -- looking back ----------------------------------------------------------

    def ask(self, question: str) -> str:
        """Answer directly from memory, without the timing gates.

        This is the person turning to it deliberately, which is a different act from
        it deciding to speak.
        """
        return self.memory.render(question, limit=5)

    @property
    def history(self) -> list[Heard]:
        return list(self._log)

    @property
    def silence_rate(self) -> float:
        """How often it said nothing. The number to watch."""
        if not self._log:
            return 1.0
        return sum(1 for h in self._log if not h.spoke) / len(self._log)

    def _record(self, heard: Heard) -> Heard:
        self._log.append(heard)
        return heard
