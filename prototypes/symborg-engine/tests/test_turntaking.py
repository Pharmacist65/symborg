"""Turn-end prediction and speculative generation.

The product's core claim is that latency is hidden behind the speaker's last words
rather than reduced. These tests pin the mechanism that makes that true.
"""

from __future__ import annotations

import unittest

from symborg_engine import Session
from symborg_engine.providers.base import Prompt
from symborg_engine.turntaking import (
    SilencePredictor, TurkishHeuristicPredictor, TurnMonitor, completion_score,
)


class _Model:
    """A model that records what it was asked, and answers instantly."""

    def __init__(self) -> None:
        self.calls: list[Prompt] = []

    def complete(self, prompt: Prompt) -> str:
        self.calls.append(prompt)
        return ('[{"text": "Evet, ağrım var.", "kind": "reply", "confidence": 0.9},'
                ' {"text": "Hayır, iyiyim.", "kind": "reply", "confidence": 0.8},'
                ' {"text": "Kastettiğim bu değil.", "kind": "repair", "confidence": 0.5}]')


class TestTurkishCues(unittest.TestCase):
    def test_finite_verb_signals_completion(self) -> None:
        for text in ["Doktora gidiyorum", "Bugün hastaneye gittim", "Yarın gelecek"]:
            with self.subTest(text=text):
                self.assertGreaterEqual(completion_score(text), 0.6)

    def test_question_particle_is_a_strong_handoff(self) -> None:
        self.assertGreaterEqual(completion_score("Ağrın var mı"), 0.85)

    def test_conjunction_signals_more_to_come(self) -> None:
        for text in ["Ben de bilmiyorum ama", "Gidiyorum çünkü", "Hem"]:
            with self.subTest(text=text):
                self.assertLess(completion_score(text), 0.3)

    def test_converb_is_grammatically_unfinished(self) -> None:
        for text in ["Eve gidip", "Koşarak", "Gelince"]:
            with self.subTest(text=text):
                self.assertLess(completion_score(text), 0.4)

    def test_trailing_comma_outranks_suffix_shape(self) -> None:
        """'artık' ends like a verb; the comma says the speaker is not done."""
        self.assertLess(completion_score("Yani ben de bilmiyorum artık,"), 0.3)

    def test_common_non_verbs_are_not_mistaken_for_verbs(self) -> None:
        for text in ["Sanırım artık", "Bundan başka", "Onun kadar"]:
            with self.subTest(text=text):
                self.assertLess(completion_score(text), 0.6)

    def test_dotted_capital_i_is_folded(self) -> None:
        self.assertGreaterEqual(completion_score("İstanbul'a gidiyorum"), 0.6)

    def test_empty_input_is_not_a_completion(self) -> None:
        self.assertEqual(completion_score("   "), 0.0)


class TestMonitor(unittest.TestCase):
    def test_fires_once_per_turn(self) -> None:
        """A second trigger would start a second generation for the same turn."""
        monitor = TurnMonitor()
        monitor.observe("Yani")
        first = monitor.observe("ağrın var mı")
        second = monitor.observe("gerçekten söyle")
        self.assertTrue(first.fired)
        self.assertFalse(second.fired)

    def test_does_not_fire_mid_clause(self) -> None:
        monitor = TurnMonitor()
        for fragment in ["Yani ben", "de bilmiyorum ama"]:
            self.assertFalse(monitor.observe(fragment).fired)

    def test_reset_allows_the_next_turn(self) -> None:
        monitor = TurnMonitor()
        monitor.observe("Ağrın var mı")
        monitor.reset()
        self.assertFalse(monitor.has_fired)
        self.assertTrue(monitor.observe("Doktoru çağırayım mı").fired)

    def test_partial_accumulates(self) -> None:
        monitor = TurnMonitor()
        monitor.observe("Yani")
        monitor.observe("ben de")
        self.assertEqual(monitor.partial, "Yani ben de")

    def test_silence_predictor_can_never_anticipate(self) -> None:
        """The control: waiting for a pause cannot fire before the turn ends."""
        monitor = TurnMonitor(predictor=SilencePredictor())
        for fragment in ["Ağrın var mı", "söyle bana", "gidiyorum"]:
            self.assertFalse(monitor.observe(fragment).fired)


class TestSpeculativeGeneration(unittest.TestCase):
    def test_generation_starts_before_the_turn_ends(self) -> None:
        model = _Model()
        session = Session(model=model)
        session.hear_partial("Yani ben")
        self.assertEqual(len(model.calls), 0, "must not generate mid-clause")
        signal = session.hear_partial("ağrın var mı")
        self.assertTrue(signal.fired)
        self.assertEqual(len(model.calls), 1, "must generate the moment the turn closes")

    def test_offer_after_speculation_costs_nothing_extra(self) -> None:
        model = _Model()
        session = Session(model=model)
        session.hear_partial("Ağrın var mı")
        result = session.offer()
        self.assertTrue(result.speculative)
        self.assertEqual(len(model.calls), 1, "the offer must reuse the speculation")
        self.assertEqual(len(result.candidates), 3)

    def test_speculation_is_consumed_only_once(self) -> None:
        model = _Model()
        session = Session(model=model)
        session.hear_partial("Ağrın var mı")
        session.offer()
        session.offer()
        self.assertEqual(len(model.calls), 2, "the second offer must generate afresh")

    def test_offer_without_speculation_still_works(self) -> None:
        model = _Model()
        session = Session(model=model)
        session.hear("Ağrın var mı")
        result = session.offer()
        self.assertFalse(result.speculative)
        self.assertEqual(len(result.candidates), 3)

    def test_speculation_sees_the_partial_turn(self) -> None:
        model = _Model()
        session = Session(model=model)
        session.hear_partial("Doktoru çağırayım mı")
        self.assertIn("Doktoru çağırayım mı", model.calls[0].user)

    def test_authorship_still_holds_over_speculation(self) -> None:
        """Generating early must not weaken the invariant."""
        session = Session(model=_Model())
        session.hear_partial("Ağrın var mı")
        result = session.offer()
        chosen = result.candidates[0]
        spoken = session.speak(session.select(0))
        self.assertEqual(spoken.utterance.text, chosen.text)
        self.assertEqual(session.spoken[0]["origin"], "user_confirmed")

    def test_completed_utterance_resets_the_monitor(self) -> None:
        session = Session(model=_Model())
        session.hear_partial("Ağrın var mı")
        session.hear("Ağrın var mı")
        self.assertFalse(session.monitor.has_fired)


if __name__ == "__main__":
    unittest.main()


class TestHardTurkishCases(unittest.TestCase):
    """Grammar facts a suffix reader gets wrong until told.

    Each of these was a measured failure on eval/turns.jsonl before it was handled.
    """

    def test_verbless_predicate_closes_a_clause(self) -> None:
        """Turkish predicates need no verb: 'Hava güzel.' has nothing to read."""
        for text in ["Bugün hava çok güzel", "Ağrım çok fazla", "Bu ilaç çok pahalı"]:
            with self.subTest(text=text):
                self.assertGreaterEqual(completion_score(text), 0.6)

    def test_predicate_word_mid_clause_does_not_fire(self) -> None:
        """The same word sits mid-clause, so the rule needs clause length."""
        self.assertLess(completion_score("Çok"), 0.6)

    def test_bare_imperative_is_a_complete_turn(self) -> None:
        """An imperative carries no suffix at all, yet the turn is finished."""
        for text in ["Doktoru ara", "Lütfen biraz bekle", "Gel"]:
            with self.subTest(text=text):
                self.assertGreaterEqual(completion_score(text), 0.6)

    def test_negative_copula_inflects_for_person(self) -> None:
        """'değilim' is not 'değil' plus a verb suffix; it needs listing."""
        for text in ["Onun kadar iyi değilim", "Hasta değilsin"]:
            with self.subTest(text=text):
                self.assertGreaterEqual(completion_score(text), 0.6)

    def test_lone_hedge_opens_a_thought(self) -> None:
        """'Sanırım' is a finite verb form but a speaker who has said only that is
        hedging what comes next."""
        self.assertLess(completion_score("Sanırım"), 0.3)
        self.assertGreaterEqual(completion_score("Sanırım iyileşiyorum"), 0.6)

    def test_correlative_waits_for_its_second_half(self) -> None:
        self.assertLess(completion_score("Hem ağrım var"), 0.4)
        self.assertGreaterEqual(completion_score("Hem ağrım var hem de uyuyamıyorum"), 0.6)

    def test_interrogative_ne_is_not_a_correlative(self) -> None:
        """Treating 'ne' as correlative suppressed genuine question endings; measured,
        that cost more than it saved."""
        self.assertGreaterEqual(completion_score("Ne zaman geleceksin"), 0.6)


class TestStreamDriving(unittest.TestCase):
    """The engine must not care where fragments come from."""

    def test_a_turn_produces_one_result(self) -> None:
        from symborg_engine import TextStream, drive

        session = Session(model=_Model())
        turns = drive(session, TextStream(["Yani ben de", "ağrın var mı"]))
        self.assertEqual(len(turns), 1)
        self.assertEqual(len(turns[0].result.candidates), 3)

    def test_lead_time_is_reported(self) -> None:
        from symborg_engine import Fragment, drive

        class _Timed:
            def __iter__(self):
                yield Fragment("Yani ben de", at_ms=0)
                yield Fragment("bilmiyorum ama", at_ms=400)
                yield Fragment("ağrın var mı", is_final=True, at_ms=800)

        turns = drive(Session(model=_Model()), _Timed())
        self.assertTrue(turns[0].anticipated)
        self.assertEqual(turns[0].lead_ms, 0, "fired on the final fragment here")

    def test_anticipation_shows_up_as_lead(self) -> None:
        from symborg_engine import Fragment, drive

        class _Timed:
            def __iter__(self):
                yield Fragment("Ağrın var mı", at_ms=0)          # fires here
                yield Fragment("söyler misin", at_ms=400)
                yield Fragment("merak ediyorum", is_final=True, at_ms=800)

        turns = drive(Session(model=_Model()), _Timed())
        self.assertTrue(turns[0].anticipated)
        self.assertEqual(turns[0].lead_ms, 800)

    def test_multiple_turns_each_reset_the_monitor(self) -> None:
        from symborg_engine import Fragment, drive

        class _Two:
            def __iter__(self):
                yield Fragment("Ağrın var mı", is_final=True, at_ms=0)
                yield Fragment("Doktoru çağırayım mı", is_final=True, at_ms=0)

        turns = drive(Session(model=_Model()), _Two())
        self.assertEqual(len(turns), 2)
        self.assertTrue(all(t.anticipated for t in turns))

    def test_blank_fragments_are_ignored(self) -> None:
        from symborg_engine import TextStream, drive

        turns = drive(Session(model=_Model()), TextStream(["", "   ", "Ağrın var mı"]))
        self.assertEqual(len(turns), 1)
