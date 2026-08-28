"""Deciding whether anyone is speaking, before the audio costs anything.

Streaming a room all day means paying for its silence, and a room is mostly silent —
measured at ~$248 a month per person for raw audio into a live transcription endpoint.
It also means the silence leaves the phone at all, and the minutes when nobody said
anything are still somebody's afternoon.
"""

from __future__ import annotations

import math
import struct
import unittest

from symborg_engine.providers.vad import SPEECH_HANGOVER_MS, Gate

RATE = 24_000
BLOCK = int(RATE * 0.02) * 2       # 20 ms of PCM16


def _quiet(seconds: float, level: int = 40) -> bytes:
    """Room tone. Never digital silence — a real microphone always has a floor."""
    return b"".join(struct.pack("<h", int(level * math.sin(i / 7.0)))
                    for i in range(int(RATE * seconds)))


def _loud(seconds: float, level: int = 6000) -> bytes:
    return b"".join(struct.pack("<h", int(level * math.sin(i / 11.0)))
                    for i in range(int(RATE * seconds)))


def _through(gate: Gate, audio: bytes) -> int:
    return sum(len(gate.filter(audio[i:i + BLOCK])) for i in range(0, len(audio), BLOCK))


class TestItHoldsBackSilence(unittest.TestCase):
    def test_a_quiet_room_costs_nothing(self):
        gate = Gate()
        self.assertEqual(_through(gate, _quiet(5.0)), 0)

    def test_speech_gets_through(self):
        gate = Gate()
        _through(gate, _quiet(2.0))
        self.assertGreater(_through(gate, _loud(2.0)), 0)

    def test_most_of_a_quiet_afternoon_never_leaves(self):
        gate = Gate()
        audio = _quiet(20.0) + _loud(3.0) + _quiet(20.0)
        passed = _through(gate, audio)
        self.assertLess(passed / len(audio), 0.25)
        self.assertGreater(passed, 0)


class TestItDoesNotEatWords(unittest.TestCase):
    """Cutting a word is expensive and passing a second of noise is not, so every
    threshold here leans the same way."""

    def test_the_onset_survives(self):
        """The first consonant of a word is usually quieter than the vowel that gave it
        away, so audio from before the gate opened goes too."""
        gate = Gate()
        _through(gate, _quiet(2.0))
        passed = _through(gate, _loud(0.5))
        self.assertGreater(passed, int(RATE * 0.5) * 2)

    def test_a_pause_inside_a_sentence_does_not_close_it(self):
        """Turkish speakers pause before the verb that ends the clause, and that verb is
        exactly what the turn-end predictor needs."""
        gate = Gate()
        _through(gate, _quiet(2.0))
        _through(gate, _loud(1.0))
        _through(gate, _quiet(0.4))            # a pause, not an ending
        self.assertTrue(gate.speaking)

    def test_the_hangover_is_generous_on_purpose(self):
        self.assertGreaterEqual(SPEECH_HANGOVER_MS, 500)

    def test_a_long_speaker_does_not_teach_it_they_are_background(self):
        """The floor only learns from quiet. Otherwise someone talking for a minute
        becomes the room, and the gate closes on them mid-sentence."""
        gate = Gate()
        _through(gate, _quiet(2.0))
        _through(gate, _loud(30.0))
        self.assertTrue(gate.speaking)
        self.assertGreater(_through(gate, _loud(1.0)), 0)


class TestItSurvivesOddInput(unittest.TestCase):
    def test_nothing_in_nothing_out(self):
        self.assertEqual(Gate().filter(b""), b"")

    def test_an_odd_length_block_does_not_crash(self):
        Gate().filter(b"\x00\x01\x02")

    def test_it_opens_when_the_recording_starts_mid_sentence(self):
        """Seeding the noise floor from the first block taught it that speech was the
        background, and it stayed shut on the person talking."""
        gate = Gate()
        self.assertGreater(_through(gate, _loud(0.5)), 0)

    def test_resetting_forgets_the_room(self):
        gate = Gate()
        _through(gate, _quiet(2.0))
        _through(gate, _loud(1.0))
        gate.reset()
        self.assertFalse(gate.speaking)


class TestItReportsWhatItSaved(unittest.TestCase):
    """The number that decides both the bill and what can honestly be promised."""

    def test_the_fraction_is_measured(self):
        gate = Gate()
        _through(gate, _quiet(10.0) + _loud(2.0) + _quiet(10.0))
        self.assertGreater(gate.passed_fraction, 0.0)
        self.assertLess(gate.passed_fraction, 0.5)

    def test_an_untouched_gate_reports_nothing(self):
        self.assertEqual(Gate().passed_fraction, 0.0)


if __name__ == "__main__":
    unittest.main()
