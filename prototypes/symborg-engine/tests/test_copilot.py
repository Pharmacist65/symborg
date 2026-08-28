"""The salience gate.

Every device in this category that failed, failed here: it spoke when it should not
have. So silence is the structure rather than the fallback, and these tests hold that
line — including against the version of me that will later want it to be more helpful.
"""

from __future__ import annotations

import unittest

from symborg_engine.copilot import Moment, Reason, SalienceGate
from symborg_engine.copilot.judge import Judgement, judge_moment
from symborg_engine.providers.base import Prompt, ProviderError


def _reply(worth_it: bool, say: str = "", score: float = 0.9) -> str:
    import json
    return json.dumps({"worth_it": worth_it, "score": score, "say": say, "why": "t"})


class _Model:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[Prompt] = []

    def complete(self, prompt: Prompt) -> str:
        self.calls.append(prompt)
        return self.reply


class _Failing:
    def complete(self, prompt: Prompt) -> str:
        raise ProviderError("down")


class TestSilenceIsTheDefault(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = SalienceGate()

    def test_mid_turn_is_never_interrupted(self) -> None:
        """Interrupting mid-sentence is the fastest way to be switched off."""
        v = self.gate.consider(Moment(partner_mid_turn=True), score=1.0)
        self.assertFalse(v.speak)
        self.assertEqual(v.reason, Reason.PARTNER_MID_TURN)

    def test_the_user_speaking_outranks_everything(self) -> None:
        v = self.gate.consider(Moment(user_speaking=True, partner_mid_turn=False), 1.0)
        self.assertEqual(v.reason, Reason.USER_SPEAKING)

    def test_muting_outranks_being_asked(self) -> None:
        v = self.gate.consider(Moment(muted=True, user_asked=True), 1.0)
        self.assertEqual(v.reason, Reason.MUTED)

    def test_a_sensitive_moment_silences_regardless_of_score(self) -> None:
        v = self.gate.consider(Moment(sensitive=True, partner_mid_turn=False), 1.0)
        self.assertEqual(v.reason, Reason.SENSITIVE_MOMENT)

    def test_a_weak_reason_is_not_a_reason(self) -> None:
        v = self.gate.consider(Moment(partner_mid_turn=False), 0.5)
        self.assertEqual(v.reason, Reason.LOW_CONFIDENCE)

    def test_a_strong_reason_at_a_clear_moment_passes(self) -> None:
        self.assertTrue(self.gate.consider(Moment(partner_mid_turn=False), 0.9).speak)


class TestFrequency(unittest.TestCase):
    """Correct and well-timed still becomes intolerable at the wrong frequency."""

    def test_speaking_twice_in_a_row_is_refused(self) -> None:
        gate = SalienceGate()
        gate.spoke(at_s=100.0)
        v = gate.consider(Moment(partner_mid_turn=False, at_s=105.0), 1.0)
        self.assertEqual(v.reason, Reason.TOO_SOON)

    def test_the_gap_eventually_opens(self) -> None:
        gate = SalienceGate(min_gap_s=10.0)
        gate.spoke(at_s=100.0)
        self.assertTrue(gate.consider(Moment(partner_mid_turn=False, at_s=115.0), 0.9).speak)

    def test_a_ceiling_holds_however_interesting_the_world_gets(self) -> None:
        gate = SalienceGate(min_gap_s=0.0, max_per_minute=2)
        gate.spoke(at_s=100.0)
        gate.spoke(at_s=101.0)
        v = gate.consider(Moment(partner_mid_turn=False, at_s=102.0), 1.0)
        self.assertEqual(v.reason, Reason.RATE_LIMIT)

    def test_the_verdict_does_not_assume_it_was_acted_on(self) -> None:
        """consider() must not count as having spoken."""
        gate = SalienceGate()
        gate.consider(Moment(partner_mid_turn=False), 0.9)
        self.assertTrue(gate.consider(Moment(partner_mid_turn=False), 0.9).speak)


class TestBeingAsked(unittest.TestCase):
    """A direct question suspends timing, not judgement."""

    def test_being_asked_bypasses_the_gap(self) -> None:
        gate = SalienceGate()
        gate.spoke(at_s=100.0)
        self.assertTrue(gate.consider(Moment(user_asked=True, at_s=101.0), 0.5).speak)

    def test_being_asked_with_nothing_to_say_still_stays_quiet(self) -> None:
        gate = SalienceGate()
        v = gate.consider(Moment(user_asked=True), 0.0)
        self.assertEqual(v.reason, Reason.NOTHING_NOTABLE)


class TestJudgeFailsToSilence(unittest.TestCase):
    """Nothing may invent a reason to speak."""

    def test_a_provider_failure_is_silence(self) -> None:
        self.assertFalse(judge_moment(_Failing(), "bir şey").worth_it)

    def test_an_unparseable_reply_is_silence(self) -> None:
        self.assertFalse(judge_moment(_Model("bunu ayrıştıramazsın"), "bir şey").worth_it)

    def test_an_empty_transcript_is_silence(self) -> None:
        model = _Model(_reply(True, "bir şey"))
        self.assertFalse(judge_moment(model, "   ").worth_it)
        self.assertEqual(model.calls, [], "must not even ask")

    def test_a_verdict_it_cannot_say_briefly_is_silence(self) -> None:
        """If it needed a paragraph, it was not a clear enough reason to interrupt."""
        long = " ".join(["kelime"] * 30)
        self.assertFalse(judge_moment(_Model(_reply(True, long)), "bir şey").worth_it)

    def test_speaking_with_nothing_to_say_is_silence(self) -> None:
        self.assertFalse(judge_moment(_Model(_reply(True, "")), "bir şey").worth_it)

    def test_a_fenced_reply_still_parses(self) -> None:
        fenced = "```json\n" + _reply(True, "12 Mart, saat iki.") + "\n```"
        self.assertTrue(judge_moment(_Model(fenced), "bir şey").worth_it)

    def test_an_empty_memory_is_stated_rather_than_left_open(self) -> None:
        """With nothing known, recall and contradiction cannot apply — say so, so the
        model does not fill the gap by inventing."""
        model = _Model(_reply(False))
        judge_moment(model, "Toplantı ne zamandı?", memory="")
        self.assertIn("boş", model.calls[0].user)


class TestWhisperLength(unittest.TestCase):
    def test_a_whisper_is_bounded(self) -> None:
        self.assertFalse(Judgement(True, 0.9, "12 Mart, saat iki.", "").is_too_long)
        self.assertTrue(Judgement(True, 0.9, " ".join(["x"] * 20), "").is_too_long)


if __name__ == "__main__":
    unittest.main()
