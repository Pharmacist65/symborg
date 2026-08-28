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
from dataclasses import dataclass, field, replace

from ..context.transcript import Transcript
from ..providers import resolve_language_model, resolve_synthesiser
from ..providers.base import LanguageModel, Synthesiser, Utterance, VoiceRef
from ..turntaking import TurnMonitor
from .addressed import Address, Wants, answer, understand
from .extract import extract
from .judge import decide
from .look import look
from .memory import Memory, Recollection
from .output import (MAX_WHISPER_WORDS, Channel, Delivery, Held, Situation,
                     route)
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
    delivery: Delivery | None = field(default=None, kw_only=True)
    address: Address | None = field(default=None, kw_only=True)
    """Set when the person turned to it rather than talked near it."""
    sighting: dict | None = field(default=None, kw_only=True)
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
                "delivery": self.delivery.to_dict() if self.delivery else None,
                "address": self.address.to_dict() if self.address else None,
                "sighting": self.sighting,
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
    situation: Situation = field(default_factory=Situation)
    """What is true around the person: whether a private channel exists, whether the
    screen can be glanced at, whether anyone else is present. Defaults to the cautious
    reading — company, no earpiece — so a caller that knows nothing gets the quiet
    behaviour."""
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
        """The next turn is meant for it. Set by a wake word or a button press."""
        self._asked = True

    # -- being spoken to -------------------------------------------------------

    def asked(self, said: str, image: bytes | None = None,
              translator=None) -> Heard:
        """The person turned to it and said something.

        The exact inverse of :meth:`turn_ended`. There, silence is the default and
        speaking must be justified; here someone deliberately addressed the device, so
        saying nothing is the failure. The salience gate does not apply, the rate limit
        does not apply, and mute does not apply — mute is this person\'s own instruction
        and so is talking to it, and the later one wins.

        Args:
            said: What they said to it.
            image: A frame from the camera, when there is one. A request to look at
                something comes back with ``needs_camera`` set and no answer until one
                arrives; nothing is invented about a picture that was never taken.
            translator: Used only for translation requests. Optional so the ordinary
                paths cost nothing.

        Returns:
            What happened, always with something said.
        """
        started = _now_ms()
        text = " ".join(said.split())
        self._asked = False
        self.monitor.reset()
        if not text:
            return self._record(Heard("", Verdict.silent(Reason.NOTHING_NOTABLE)))

        self.transcript.add_text(text, speaker="user")
        request = understand(self.model, text)

        if request.want is Wants.LOOK and image is None:
            # Nothing to answer from yet. Saying so is the answer.
            return self._deliver(text, request, "Telefonu ona doğru tut.",
                                 started, perishable=True)

        if request.want is Wants.LOOK:
            sighting = look(self.model, image, request.query or "Bu ne?")
            spoken = sighting.whisper or sighting.seen or "Göremedim."
            return self._deliver(text, request, spoken, started,
                                 sighting=sighting.to_dict())

        if request.want is Wants.TRANSLATE:
            if translator is None:
                return self._deliver(text, request, "Çeviri şu an kapalı.", started)
            rendering = translator.outgoing(request.query or text, speak=False)
            return self._deliver(text, request,
                                 rendering.text or "Çeviremedim.", started)

        if request.want is Wants.REMEMBER:
            # Deliberate. A person saying "bunu unutma" outranks any confidence score,
            # so this goes in whole rather than through the extractor\'s judgement.
            self.memory.keep(Recollection(request.query or text, kind="fact",
                                          source=text, confidence=1.0))
            return self._deliver(text, request, "Tamam, aklımda.", started)

        if request.want is Wants.FORGET:
            removed = self.memory.forget(lambda item: True) if _is_total(request.query) \
                else self.memory.forget(
                    lambda item: bool(_tokens_of(request.query) & item.tokens))
            spoken = "Sildim." if removed else "Öyle bir şey yok zaten."
            return self._deliver(text, request, spoken, started)

        if request.want is Wants.UNCLEAR:
            return self._deliver(text, request, request.say_if_unclear, started)

        known = self.memory.render(request.query or text, asked=True)
        return self._deliver(text, request, answer(self.model, request.query or text,
                                                   known), started)

    def _deliver(self, text: str, request: Address, spoken: str, started: int,
                 sighting: dict | None = None, perishable: bool = False) -> Heard:
        """Say it. Being addressed suspends the gate, not the routing: a private channel
        is still chosen over a loudspeaker in a room full of people."""
        situation = self.situation
        if situation.user_speaking:
            # They just finished asking, so this flag is stale rather than true.
            situation = replace(situation, user_speaking=False)
        delivery = route(spoken, situation, perishable=perishable)
        if not delivery.delivered and delivery.held is Held.TOO_LONG:
            spoken = " ".join(spoken.split()[:MAX_WHISPER_WORDS])
            delivery = route(spoken, situation, perishable=perishable)

        utterance = None
        if delivery.channel in (Channel.EAR, Channel.ROOM):
            utterance = self.synthesiser.synthesise(delivery.text, self.voice)
        self.gate.spoke(self.clock())
        return self._record(Heard(
            text, Verdict.worth_it(1.0), said=delivery.text or spoken,
            utterance=utterance, delivery=delivery, address=request,
            sighting=sighting, latency_ms=_now_ms() - started,
        ))

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

        delivery = route(judgement.say, self.situation,
                         perishable=judgement.perishable)
        if not delivery.delivered:
            # Worth saying, with nowhere to say it. Not the same as having nothing to
            # say, and the reason is kept so a caller can show why it stayed quiet.
            return self._record(Heard(
                text, Verdict.silent(Reason.NOTHING_NOTABLE, judgement.score),
                remembered=self._store(text), delivery=delivery,
                latency_ms=_now_ms() - started))

        utterance = None
        if delivery.channel in (Channel.EAR, Channel.ROOM):
            utterance = self.synthesiser.synthesise(delivery.text, self.voice)
        self.gate.spoke(at_s)
        return self._record(Heard(
            transcript=text, verdict=verdict, said=delivery.text,
            remembered=self._store(text), utterance=utterance, delivery=delivery,
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


_TOTAL = ("hepsini", "her şeyi", "hiçbir şey", "tamamen", "tümünü", "bütün")


def _is_total(query: str) -> bool:
    """Whether a request to forget means everything. Erasing more than was asked is the
    worse mistake, so this stays narrow and deliberate."""
    lowered = query.replace("İ", "i").replace("I", "ı").lower()
    return any(word in lowered for word in _TOTAL)


def _tokens_of(query: str) -> set:
    from .memory import _tokens
    return _tokens(query)
