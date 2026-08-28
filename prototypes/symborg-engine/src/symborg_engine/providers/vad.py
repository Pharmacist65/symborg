"""Deciding whether anyone is speaking, before the audio costs anything.

Streaming a room to a transcription endpoint all day means paying for its silence, and
a room is mostly silent. Worse, it means the silence leaves the phone at all — the
minutes when nobody said anything are still somebody's afternoon.

So this sits in front of everything: cheap, local, and biased towards letting speech
through. Cutting a word is expensive and passing a second of noise is not, which is why
the hangover is long and the threshold adapts to the room rather than to a constant
somebody picked in a quiet office.

Energy and zero-crossing rate only. No model, no dependency, no network — it has to be
cheap enough to run on every frame of an eight-hour day on an old phone.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass, field

__all__ = ["Gate", "SPEECH_HANGOVER_MS", "FRAME_MS"]

FRAME_MS = 20
"""Short enough to catch the start of a word, long enough that the arithmetic is cheap."""

SPEECH_HANGOVER_MS = 900
"""How long to keep passing audio after speech stops.

Generous on purpose. A pause inside a sentence is ordinary — Turkish speakers pause
before the verb that ends the clause — and cutting there loses exactly the word the
turn-end predictor needs. Nine hundred milliseconds costs a fraction of a cent; a
truncated turn costs the whole point.
"""

LEAD_IN_MS = 300
"""How much audio before speech was detected to send anyway. Onsets are quiet — the
first consonant of a word is often below the threshold that noticed the vowel."""

_FLOOR_ALPHA = 0.02
"""How fast the noise floor follows the room. Slow: a passing lorry should not raise the
floor above the person sitting opposite."""

_SPEECH_OVER_FLOOR = 3.2
"""How far above the noise floor counts as speech. Measured in linear amplitude, not dB,
because the arithmetic runs on every frame."""

_MIN_FLOOR = 60.0
"""Below this the microphone is effectively silent and the ratio becomes meaningless —
in a genuinely quiet room, a floor near zero makes any rustle look like shouting."""


@dataclass(slots=True)
class Gate:
    """Passes audio while someone is speaking, and holds it back otherwise.

        gate = Gate()
        for block in microphone:
            speech = gate.filter(block)
            if speech:
                send(speech)

    Feed it 24 kHz mono PCM16. What comes back is the same audio, or nothing.
    """

    sample_rate: int = 24_000
    hangover_ms: int = SPEECH_HANGOVER_MS
    lead_in_ms: int = LEAD_IN_MS

    _floor: float = field(default=0.0, init=False, repr=False)
    _quiet_ms: int = field(default=10_000, init=False, repr=False)
    _lead: list[bytes] = field(default_factory=list, init=False, repr=False)
    _lead_ms: int = field(default=0, init=False, repr=False)
    _passed_ms: int = field(default=0, init=False, repr=False)
    _held_ms: int = field(default=0, init=False, repr=False)

    @property
    def speaking(self) -> bool:
        return self._quiet_ms < self.hangover_ms

    @property
    def passed_fraction(self) -> float:
        """How much of the day actually left the device. The number that decides both
        the bill and what can honestly be promised."""
        total = self._passed_ms + self._held_ms
        return self._passed_ms / total if total else 0.0

    def filter(self, pcm16: bytes) -> bytes:
        """Return the audio if it should be sent, or empty bytes if it should not."""
        if not pcm16:
            return b""

        samples = array.array("h")
        try:
            samples.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
        except ValueError:
            return pcm16          # not something we can measure; do not swallow it
        if not samples:
            return b""

        duration_ms = int(1000 * len(samples) / self.sample_rate)
        energy = _rms(samples)

        if self._floor <= 0.0:
            # Start low, not at whatever the first block happened to contain. Seeding
            # the floor from the first block means a recording that starts mid-sentence
            # teaches the gate that speech is the background, and it stays shut on the
            # person talking. Starting low lets noise through until the floor catches
            # up, which is the cheap direction to be wrong in.
            self._floor = _MIN_FLOOR
        loud = energy > max(self._floor * _SPEECH_OVER_FLOOR, _MIN_FLOOR * 1.5)

        if loud:
            self._quiet_ms = 0
        else:
            self._quiet_ms += duration_ms
            # The floor only learns from quiet, or a long speaker teaches it that their
            # own voice is the background and the gate closes on them mid-sentence.
            self._floor += _FLOOR_ALPHA * (energy - self._floor)
            self._floor = max(self._floor, 1.0)

        if not self.speaking:
            self._held_ms += duration_ms
            self._remember(pcm16, duration_ms)
            return b""

        self._passed_ms += duration_ms
        if self._lead:
            # Speech just started. Send what came immediately before it too: the first
            # consonant of a word is usually quieter than the vowel that gave it away.
            lead = b"".join(self._lead)
            self._lead.clear()
            self._lead_ms = 0
            return lead + pcm16
        return pcm16

    def _remember(self, pcm16: bytes, duration_ms: int) -> None:
        self._lead.append(pcm16)
        self._lead_ms += duration_ms
        while self._lead_ms > self.lead_in_ms and len(self._lead) > 1:
            self._lead_ms -= int(1000 * (len(self._lead[0]) // 2) / self.sample_rate)
            self._lead.pop(0)

    def reset(self) -> None:
        self._floor = 0.0
        self._quiet_ms = 10_000
        self._lead.clear()
        self._lead_ms = 0


def _rms(samples: array.array) -> float:
    total = 0
    for s in samples:
        total += s * s
    return math.sqrt(total / len(samples))
