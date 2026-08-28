"""When the person is talking to it, rather than near it.

The inverse of the salience tests. There the line held is that it must not speak; here
it is that it must — being asked and saying nothing is the failure this path exists to
prevent.
"""

from __future__ import annotations

import json
import unittest

from symborg_engine.copilot import Copilot, Memory, Recollection, Situation
from symborg_engine.copilot.addressed import (Address, Wants, answer, understand)
from symborg_engine.providers.base import Prompt, ProviderError
from symborg_engine.providers.offline import OfflineLanguageModel, OfflineSynthesiser


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


def _want(want: str, query: str = "", unclear: str = "Ne?") -> str:
    return json.dumps({"want": want, "query": query, "say_if_unclear": unclear},
                      ensure_ascii=False)


class TestTheCheapPathCatchesOnlyTheCertain(unittest.TestCase):
    """A shortcut that guesses is worse than no shortcut: it cannot be overruled."""

    def test_keeping_and_dropping_are_not_confused(self):
        """"Bunu unutma" is keep and "bunu unut" is drop, so the longer phrase has to be
        tested first or every request to remember deletes instead."""
        model = _Model(_want("unclear"))
        self.assertIs(understand(model, "Toplantıyı unutma.").want, Wants.REMEMBER)
        self.assertIs(understand(model, "Bunu unut.").want, Wants.FORGET)
        self.assertEqual(model.calls, [])       # neither needed the model

    def test_a_cue_does_not_match_inside_a_longer_word(self):
        """"ne bu" matched inside "İngilizcesi ne bunun", so asking for a translation
        opened the camera."""
        model = _Model(_want("translate", "yarın dokuzda buluşalım"))
        got = understand(model, "İngilizcesi ne bunun: yarın dokuzda buluşalım")
        self.assertIs(got.want, Wants.TRANSLATE)

    def test_an_unmistakable_look_still_shortcuts(self):
        model = _Model(_want("unclear"))
        self.assertIs(understand(model, "Baksana şuna.").want, Wants.LOOK)
        self.assertEqual(model.calls, [])

    def test_translation_always_asks_the_model(self):
        """The cues find the intent easily; separating the payload from the request is
        what needs judgement, and getting it wrong reads the request to a stranger."""
        model = _Model(_want("translate", "hesabı alabilir miyiz"))
        got = understand(model, "Bunu İngilizce nasıl derim: hesabı alabilir miyiz")
        self.assertEqual(got.query, "hesabı alabilir miyiz")
        self.assertEqual(len(model.calls), 1)


class TestItNeverComesBackWithNothing(unittest.TestCase):
    def test_a_provider_failure_falls_back_to_memory(self):
        """It cannot tell what was wanted, but it was definitely addressed. Guessing
        "look" would open a camera nobody pointed at anything."""
        self.assertIs(understand(_Failing(), "bir şey sordu").want, Wants.ANSWER)

    def test_an_unparseable_reply_falls_back_to_memory(self):
        self.assertIs(understand(_Model("not json"), "bir şey").want, Wants.ANSWER)

    def test_an_unknown_want_is_unclear_not_a_crash(self):
        self.assertIs(understand(_Model(_want("something_else"))).want
                      if False else understand(_Model(_want("something_else")), "x").want,
                      Wants.UNCLEAR)

    def test_an_empty_request_asks_again(self):
        self.assertTrue(Address().say_if_unclear)


class TestAnsweringDirectly(unittest.TestCase):
    """Not knowing is an answer. A confident guess is not."""

    def test_nothing_known_says_so_without_asking_the_model(self):
        model = _Model(json.dumps({"say": "uydurma", "knew": True}))
        self.assertEqual(answer(model, "toplantı ne zamandı", ""), "Bunu bilmiyorum.")
        self.assertEqual(model.calls, [])

    def test_a_provider_failure_still_says_something(self):
        self.assertTrue(answer(_Failing(), "soru", "bir şey"))

    def test_a_long_answer_is_cut_rather_than_dropped(self):
        """Elsewhere too long means say nothing. Here someone is waiting."""
        long = " ".join(["kelime"] * 40)
        model = _Model(json.dumps({"say": long, "knew": True}))
        got = answer(model, "soru", "bir şey")
        self.assertTrue(got)
        self.assertLessEqual(len(got.split()), 14)


class TestBeingAskedSuspendsTheGate(unittest.TestCase):
    """Everywhere else silence is the default. Here it is the failure."""

    def _copilot(self, **kw) -> Copilot:
        return Copilot(model=kw.pop("model", OfflineLanguageModel()),
                       synthesiser=OfflineSynthesiser(),
                       memory=kw.pop("memory", Memory()),
                       situation=kw.pop("situation", Situation(earpiece=True)),
                       clock=lambda: 0.0, **kw)

    def test_the_rate_limit_does_not_apply(self):
        copilot = self._copilot(model=_Model(_want("unclear")))
        for _ in range(5):
            self.assertTrue(copilot.asked("bir şey sordum").spoke)

    def test_muting_does_not_apply(self):
        """Mute is this person's instruction and so is talking to it; the later wins."""
        copilot = self._copilot(model=_Model(_want("unclear")), muted=True)
        self.assertTrue(copilot.asked("bir şey sordum").spoke)

    def test_asking_to_look_without_a_frame_says_so(self):
        copilot = self._copilot(model=_Model(_want("look", "bu ne")))
        heard = copilot.asked("Baksana şuna.")
        self.assertTrue(heard.spoke)
        self.assertIn("tut", heard.said)
        self.assertIsNone(heard.sighting)

    def test_deliberate_remembering_bypasses_the_extractor(self):
        """A person saying "bunu unutma" outranks any confidence score."""
        copilot = self._copilot()
        copilot.asked("Kızımın doğum günü 12 Mart, bunu unutma.")
        self.assertEqual(len(copilot.memory.items), 1)
        self.assertEqual(copilot.memory.items[0].confidence, 1.0)

    def test_forgetting_everything_means_everything(self):
        memory = Memory()
        memory.keep(Recollection("Toplantı salı.", kind="date"))
        memory.keep(Recollection("Bütçe 150 bin.", kind="number"))
        copilot = self._copilot(memory=memory)
        copilot.asked("Her şeyi unut.")
        self.assertEqual(memory.items, [])

    def test_forgetting_one_thing_leaves_the_rest(self):
        memory = Memory()
        memory.keep(Recollection("Toplantı salı saat ikide.", kind="date"))
        memory.keep(Recollection("Bütçe 150 bin.", kind="number"))
        copilot = self._copilot(memory=memory)
        copilot.asked("Toplantıyı unut.")
        self.assertEqual([i.text for i in memory.items], ["Bütçe 150 bin."])

    def test_a_translation_request_without_a_translator_says_so(self):
        copilot = self._copilot(model=_Model(_want("translate", "merhaba")))
        heard = copilot.asked("Bunu çevir: merhaba")
        self.assertTrue(heard.spoke)

    def test_an_empty_request_is_not_an_answer(self):
        self.assertFalse(self._copilot().asked("   ").spoke)


class TestAskedStillRoutes(unittest.TestCase):
    """Being addressed suspends the gate, not the routing. A loudspeaker in a meeting
    still tells everyone present."""

    def test_it_prefers_the_ear(self):
        copilot = Copilot(model=_Model(_want("unclear")), synthesiser=OfflineSynthesiser(),
                          memory=Memory(), situation=Situation(earpiece=True),
                          clock=lambda: 0.0)
        self.assertEqual(copilot.asked("bir şey").delivery.channel.value, "ear")

    def test_with_company_and_no_earpiece_it_uses_the_screen(self):
        copilot = Copilot(model=_Model(_want("unclear")), synthesiser=OfflineSynthesiser(),
                          memory=Memory(),
                          situation=Situation(others_present=True, screen_visible=True),
                          clock=lambda: 0.0)
        self.assertEqual(copilot.asked("bir şey").delivery.channel.value, "screen")


if __name__ == "__main__":
    unittest.main()


class TestItDoesNotTalkAboutItself(unittest.TestCase):
    """The prompt's own vocabulary reaching a person's ear. "Bilmiyorum, BİLDİKLERİN'de
    sunum bilgisi yok" is the machine describing its storage to someone who asked about
    a presentation."""

    def test_a_leak_becomes_a_plain_answer(self):
        for leak in ("BİLDİKLERİN'de yok.", "Kayıtlarımda bulamadım.",
                     "Hafızamda böyle bir şey yok.", "JSON'da yok."):
            with self.subTest(leak=leak):
                model = _Model(json.dumps({"say": leak, "knew": False}))
                self.assertEqual(answer(model, "soru", "bir şey"), "Bunu bilmiyorum.")

    def test_an_ordinary_answer_is_untouched(self):
        model = _Model(json.dumps({"say": "Toplantı salı saat ikide.", "knew": True}))
        self.assertEqual(answer(model, "ne zaman", "bir şey"), "Toplantı salı saat ikide.")
