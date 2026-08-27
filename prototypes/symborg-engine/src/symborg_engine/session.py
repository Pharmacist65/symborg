"""Session orchestration: the loop from conversation to spoken sentence.

Owns the sequence — ingest, generate, offer, select, authorise, speak, learn — and the
timings for each stage. Latency is tracked as a first-class result because in this
product a correct sentence delivered after the conversation has moved on has failed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .authorship import AuthorizationError, AuthorizationLedger, SpeechAuthorization
from .candidate import Candidate, Offer
from .context.transcript import Transcript
from .context.vault import Vault
from .generate.candidates import expand_abbreviation, generate_candidates
from .providers import resolve_language_model
from .providers.base import (
    LanguageModel, Synthesiser, TranscriptChunk, Utterance, VoiceRef,
)
from .providers.offline import OfflineSynthesiser
from .turntaking import TurnMonitor, TurnSignal

__all__ = ["Session", "OfferResult", "SpeakResult"]


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True, frozen=True)
class OfferResult:
    """Candidates presented to the person, plus how long they took to produce."""

    offer: Offer
    latency_ms: int
    degraded: bool = False
    speculative: bool = False
    """Whether these candidates were generated before the turn actually ended.

    When true, ``latency_ms`` was spent while the other person was still speaking, so
    the delay the user experiences is roughly zero rather than the value reported."""
    lead_ms: int = 0
    """How long before the turn ended that generation started. This is the number the
    whole design turns on: it is what converts a 1.4-second call into no wait at all."""

    @property
    def candidates(self) -> tuple[Candidate, ...]:
        return self.offer.candidates

    @property
    def is_empty(self) -> bool:
        return len(self.offer) == 0

    def to_dict(self) -> dict:
        return {"offer": self.offer.to_dict(), "latency_ms": self.latency_ms,
                "degraded": self.degraded, "speculative": self.speculative,
                "lead_ms": self.lead_ms}


@dataclass(slots=True, frozen=True)
class SpeakResult:
    """A sentence the person selected, synthesised in their voice."""

    utterance: Utterance
    latency_ms: int

    def to_dict(self) -> dict:
        return {"text": self.utterance.text, "voice_id": self.utterance.voice_id,
                "mime_type": self.utterance.mime_type,
                "audio_bytes": len(self.utterance.audio), "latency_ms": self.latency_ms}


@dataclass(slots=True)
class Session:
    """One conversation with one person.

    Construct with no arguments to get a fully working offline session; pass providers
    to use real ones. The public flow is deliberately narrow:

        session.hear("Ağrın var mı?")
        result = session.offer()
        token  = session.select(0)       # only path to speech
        spoken = session.speak(token)
    """

    model: LanguageModel | None = None
    synthesiser: Synthesiser | None = None
    voice: VoiceRef = field(default_factory=lambda: VoiceRef(voice_id="offline"))
    vault: Vault = field(default_factory=Vault)
    transcript: Transcript = field(default_factory=Transcript)
    candidate_count: int = 3
    monitor: TurnMonitor = field(default_factory=TurnMonitor)
    _ledger: AuthorizationLedger = field(
        default_factory=AuthorizationLedger, init=False, repr=False, compare=False,
    )
    _current: Offer | None = field(default=None, init=False, repr=False, compare=False)
    _rejections: list[str] = field(
        default_factory=list, init=False, repr=False, compare=False,
    )
    _speculation: OfferResult | None = field(default=None, init=False, repr=False, compare=False)
    _spec_started_ms: int = field(default=0, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.model = resolve_language_model(self.model)
        if self.synthesiser is None:
            self.synthesiser = OfflineSynthesiser()

    # -- input -----------------------------------------------------------------

    def hear(self, text: str, speaker: str = "partner") -> None:
        """Record a completed utterance near the person.

        Ends the current turn: any speculation still in flight is either used by the
        next :meth:`offer` or discarded there.
        """
        self.transcript.add_text(text, speaker=speaker)
        self.monitor.reset()

    def hear_partial(self, text: str) -> TurnSignal:
        """Feed a fragment of speech that is still in progress.

        This is the entry point the whole design turns on. Each fragment is scored for
        how likely it is that the speaker has just finished, and when that crosses the
        threshold generation starts immediately — while they are still talking — so the
        candidates are ready the moment the turn actually ends.

        Returns:
            The signal for this fragment, including whether generation was triggered.
        """
        signal = self.monitor.observe(text)
        if signal.fired:
            self._speculate(self.monitor.partial)
        return signal

    def _speculate(self, partial: str) -> None:
        """Generate against a turn that has not finished yet."""
        started = _now_ms()
        self._spec_started_ms = started
        scratch = Transcript(window_turns=self.transcript.window_turns)
        for chunk in self.transcript.chunks:
            scratch.add(chunk)
        scratch.add_text(partial, speaker="partner")

        candidates = generate_candidates(
            self.model, scratch, self.vault, n=self.candidate_count,
        )
        offer = Offer(candidates=tuple(candidates))
        self._speculation = OfferResult(
            offer=offer,
            latency_ms=max(0, _now_ms() - started),
            degraded=not candidates,
            speculative=True,
        )

    def ingest(self, chunk: TranscriptChunk) -> None:
        """Record a chunk from a transcriber."""
        self.transcript.add(chunk)

    # -- offering --------------------------------------------------------------

    def offer(self) -> OfferResult:
        """Present candidates for the turn that just ended.

        If speculation fired during the turn and produced something usable, it is
        served immediately: the work already happened behind the speaker's last words,
        and the person waits for nothing. Otherwise this falls back to generating now,
        which is correct but slow enough to be noticed.

        An empty offer is a valid outcome: when the engine has nothing useful to say,
        offering nothing is better than offering something wrong.
        """
        ready = self._speculation
        self._speculation = None
        if ready is not None and not ready.is_empty:
            lead = max(0, _now_ms() - self._spec_started_ms)
            self._current = ready.offer
            return OfferResult(
                offer=ready.offer, latency_ms=ready.latency_ms,
                degraded=False, speculative=True, lead_ms=lead,
            )

        started = _now_ms()
        candidates = generate_candidates(
            self.model, self.transcript, self.vault, n=self.candidate_count,
        )
        return self._present(candidates, started)

    def offer_expansion(self, abbreviation: str) -> OfferResult:
        """Expand a terse input into candidates, then present them.

        Expansion is not a shortcut past authorship: the result is an ordinary offer
        and still requires an explicit selection.
        """
        started = _now_ms()
        candidates = expand_abbreviation(
            self.model, abbreviation, self.transcript, self.vault, n=self.candidate_count,
        )
        return self._present(candidates, started)

    def _present(self, candidates: list[Candidate], started_ms: int) -> OfferResult:
        offer = Offer(candidates=tuple(candidates))
        self._current = offer
        return OfferResult(
            offer=offer,
            latency_ms=max(0, _now_ms() - started_ms),
            degraded=not candidates,
        )

    # -- selection: the only path to speech ------------------------------------

    def select(self, index: int) -> SpeechAuthorization:
        """Record the person's explicit selection and mint an authorisation.

        This is the only function in the engine that can produce a token, and a token is
        the only thing :meth:`speak` accepts.

        Raises:
            AuthorizationError: if there is no live offer, or the index was not offered.
        """
        if self._current is None:
            raise AuthorizationError("no_active_offer")
        token = self._ledger.authorise(self._current, index)
        self._current = None
        return token

    def reject(self, note: str = "") -> None:
        """Record that none of the candidates were right, and clear the offer."""
        if note:
            self._rejections.append(note)
        if self._current is not None:
            self._current.consumed = True
        self._current = None

    # -- output ----------------------------------------------------------------

    def speak(self, authorization: SpeechAuthorization) -> SpeakResult:
        """Synthesise an authorised sentence.

        Takes a token, never raw text. There is no other route from generated text to
        audio, which is what makes the authorship guarantee enforceable rather than
        merely intended.

        Raises:
            AuthorizationError: if the token is forged, expired, or already used.
        """
        started = _now_ms()
        text = self._ledger.redeem(authorization)
        utterance = self.synthesiser.synthesise(text, self.voice)
        self.vault.remember_accepted(text)
        self.transcript.add_text(text, speaker="user")
        return SpeakResult(utterance=utterance, latency_ms=max(0, _now_ms() - started))

    # -- audit -----------------------------------------------------------------

    @property
    def spoken(self) -> list[dict]:
        """Every sentence this session actually spoke, all user-confirmed."""
        return self._ledger.utterances

    @property
    def rejections(self) -> list[str]:
        return list(self._rejections)
