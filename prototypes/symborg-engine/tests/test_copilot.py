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


class TestMemoryKeepsLittle(unittest.TestCase):
    """The difference between a recording and a memory is selection."""

    def setUp(self) -> None:
        from symborg_engine.copilot import Memory
        self.memory = Memory()

    def test_the_same_fact_is_not_kept_twice(self) -> None:
        """Repetition is normal in conversation; five copies of one fact is not."""
        from symborg_engine.copilot import Recollection
        self.assertTrue(self.memory.keep(Recollection("Bütçe 150 bin olarak belirlendi", kind="number")))
        self.assertFalse(self.memory.keep(Recollection("Bütçe 150 bin olarak belirlendi", kind="number")))
        self.assertEqual(len(self.memory.items), 1)

    def test_an_empty_recollection_is_not_kept(self) -> None:
        from symborg_engine.copilot import Recollection
        self.assertFalse(self.memory.keep(Recollection("   ")))

    def test_an_unknown_kind_falls_back_rather_than_raising(self) -> None:
        from symborg_engine.copilot import Recollection
        self.assertEqual(Recollection("bir şey", kind="telepathy").kind, "fact")


class TestRecall(unittest.TestCase):
    def setUp(self) -> None:
        from symborg_engine.copilot import Memory, Recollection
        self.memory = Memory()
        for text, kind in [
            ("Meze Han, Moda'daki restorana dün akşam gidildi.", "fact"),
            ("Kerem Yıldız, Vega Yazılım'da ürün müdürü.", "person"),
            ("Toplantı salı saat 14:00'a alındı.", "date"),
            ("Bütçe 150 bin.", "number"),
        ]:
            self.memory.keep(Recollection(text, kind=kind))

    def test_turkish_suffixes_do_not_break_recall(self) -> None:
        """'restoranın' and 'restorana' are the same word; exact matching says
        otherwise, and recall missed what it was literally asked for."""
        found = self.memory.recall("o restoranın adı neydi", limit=1)
        self.assertIn("Meze Han", found[0].text)

    def test_a_forgotten_word_is_found_by_the_kind_of_thing_it_was(self) -> None:
        """The case the product exists for: the person cannot supply the word they
        would have searched with."""
        found = self.memory.recall("adamın adı neydi", limit=1)
        self.assertIn("Kerem", found[0].text)

    def test_naming_the_thing_beats_guessing_its_category(self) -> None:
        """'restoranın adı' cues both a place and a person; the named one must win."""
        found = self.memory.recall("o restoranın adı neydi", limit=1)
        self.assertIn("Meze", found[0].text)

    def test_recall_returns_nothing_rather_than_something_irrelevant(self) -> None:
        self.assertEqual(self.memory.recall("hava nasıldı"), [])

    def test_render_is_empty_when_nothing_is_known(self) -> None:
        """The judge must be told plainly it knows nothing, not left to fill a gap."""
        self.assertEqual(self.memory.render("hava nasıldı"), "")


class TestMemoryIsThePersons(unittest.TestCase):
    """A memory a person cannot edit is surveillance with a friendly name."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        from symborg_engine.copilot import Memory, Recollection
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "memory.jsonl"
        self.memory = Memory.open(self.path)
        for text, kind in [("Bütçe 150 bin.", "number"), ("Kerem Yıldız, ürün müdürü.", "person")]:
            self.memory.keep(Recollection(text, kind=kind))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_memory_survives_a_restart(self) -> None:
        from symborg_engine.copilot import Memory
        self.assertEqual(len(Memory.open(self.path).items), 2)

    def test_a_person_can_forget_one_thing(self) -> None:
        from symborg_engine.copilot import Memory
        removed = self.memory.forget(lambda i: i.kind == "person")
        self.assertEqual(removed, 1)
        self.assertEqual(len(Memory.open(self.path).items), 1)

    def test_a_person_can_forget_everything(self) -> None:
        from symborg_engine.copilot import Memory
        self.memory.forget_all()
        self.assertEqual(Memory.open(self.path).items, [])

    def test_a_corrupt_line_does_not_hide_the_rest(self) -> None:
        from symborg_engine.copilot import Memory
        self.path.write_text('{"text": "bir", "kind": "fact"}\nbroken\n'
                             '{"text": "iki", "kind": "fact"}\n', encoding="utf-8")
        self.assertEqual([i.text for i in Memory.open(self.path).items], ["bir", "iki"])

    def test_an_unwritable_store_does_not_break_the_conversation(self) -> None:
        from symborg_engine.copilot import Memory, Recollection
        memory = Memory.open("/nonexistent-root/x/memory.jsonl")
        self.assertTrue(memory.keep(Recollection("bir şey", kind="fact")))


class TestExtractionKeepsAlmostNothing(unittest.TestCase):
    def test_a_provider_failure_keeps_nothing(self) -> None:
        from symborg_engine.copilot import extract
        self.assertEqual(extract(_Failing(), "toplantı salı"), [])

    def test_an_unparseable_reply_keeps_nothing(self) -> None:
        from symborg_engine.copilot import extract
        self.assertEqual(extract(_Model("nope"), "toplantı salı"), [])

    def test_a_low_confidence_item_is_dropped(self) -> None:
        """An uncertain memory is worse than none: it will be recalled as fact."""
        import json
        from symborg_engine.copilot import extract
        reply = json.dumps({"items": [{"text": "belki salı", "kind": "date", "confidence": 0.3}]})
        self.assertEqual(extract(_Model(reply), "belki salı olur"), [])

    def test_a_turn_cannot_yield_unlimited_memories(self) -> None:
        import json
        from symborg_engine.copilot import extract
        items = [{"text": f"şey {i}", "kind": "fact", "confidence": 0.9} for i in range(10)]
        got = extract(_Model(json.dumps({"items": items})), "uzun konuşma")
        self.assertLessEqual(len(got), 4)
