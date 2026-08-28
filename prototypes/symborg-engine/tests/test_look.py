"""Asking about something in front of the person.

The mushroom question is the first thing anyone asks of a device like this, and the one
that can kill someone. A model that is eighty per cent sure will say "edible", and
eighty per cent is a coin flip taken with your life a few times a year.
"""

from __future__ import annotations

import json
import unittest

from symborg_engine.copilot.look import MAX_WHISPER_WORDS, Sighting, look
from symborg_engine.providers.base import Prompt, ProviderError

IMAGE = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


def _reply(**kw) -> str:
    payload = {"seen": "kahverengi şapkalı mantar", "could_be": ["agarik"],
               "missing": "lamel rengi", "confidence": 0.5,
               "irreversible": False, "whisper": "Emin değilim."}
    payload.update(kw)
    return json.dumps(payload, ensure_ascii=False)


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


class TestItNeverGrantsPermission(unittest.TestCase):
    """The guarantee. Asked for in the prompt and enforced in code, because a prompt is
    a request and this needs to be a promise."""

    def test_an_edible_verdict_is_replaced(self):
        model = _Model(_reply(whisper="Bu çayır mantarı, rahatlıkla yenir.",
                              confidence=0.95, irreversible=False))
        sighting = look(model, IMAGE, "Bunu yiyebilir miyim?")
        self.assertNotIn("yenir", sighting.whisper)
        self.assertIn("sormadan", sighting.whisper)

    def test_every_permitting_word_is_caught(self):
        for granted in ("yenir", "yenebilir", "güvenli", "zararsız", "sorun yok",
                        "afiyet olsun", "edible", "safe to eat"):
            with self.subTest(granted=granted):
                model = _Model(_reply(whisper=f"Bu mantar {granted}."))
                self.assertNotIn(granted,
                                 look(model, IMAGE, "yiyebilir miyim?").whisper)

    def test_the_question_alone_marks_it_irreversible(self):
        """Even when the model says otherwise. It is the person's intent that makes an
        action unrecoverable, not the model's reading of the picture."""
        model = _Model(_reply(irreversible=False))
        self.assertTrue(look(model, IMAGE, "Bu mantarı yiyebilir miyim?").irreversible)

    def test_an_ordinary_question_is_left_alone(self):
        model = _Model(_reply(whisper="Kablosuz kulaklık kutusu.", irreversible=False))
        sighting = look(model, IMAGE, "Bu ne?")
        self.assertEqual(sighting.whisper, "Kablosuz kulaklık kutusu.")
        self.assertFalse(sighting.irreversible)

    def test_the_prompt_says_so_too(self):
        model = _Model(_reply())
        look(model, IMAGE, "Bunu yiyebilir miyim?")
        self.assertIn("DİKKAT", model.calls[0].user)


class TestItSaysWhatItCannotSee(unittest.TestCase):
    def test_the_alternatives_survive(self):
        model = _Model(_reply(could_be=["çayır mantarı", "yeşil bölmeli amanita"]))
        self.assertEqual(len(look(model, IMAGE, "Bu ne?").could_be), 2)

    def test_blank_alternatives_are_dropped(self):
        model = _Model(_reply(could_be=["bir şey", "  ", ""]))
        self.assertEqual(look(model, IMAGE, "Bu ne?").could_be, ("bir şey",))

    def test_confidence_is_bounded(self):
        self.assertEqual(look(_Model(_reply(confidence=3.0)), IMAGE, "?").confidence, 1.0)
        self.assertEqual(look(_Model(_reply(confidence=-1)), IMAGE, "?").confidence, 0.0)


class TestFailingIsQuiet(unittest.TestCase):
    """A camera that answers wrongly is worse than one that says nothing, and this is
    the one place in the engine where being wrong has a physical cost."""

    def test_no_image_no_call(self):
        model = _Model(_reply())
        self.assertFalse(look(model, b"", "Bu ne?"))
        self.assertEqual(model.calls, [])

    def test_a_provider_failure_shows_nothing(self):
        self.assertFalse(look(_Failing(), IMAGE, "Bu ne?"))

    def test_an_unparseable_reply_shows_nothing(self):
        self.assertFalse(look(_Model("not json"), IMAGE, "Bu ne?"))

    def test_a_long_whisper_is_dropped(self):
        long = " ".join(["kelime"] * (MAX_WHISPER_WORDS + 1))
        self.assertEqual(look(_Model(_reply(whisper=long)), IMAGE, "Bu ne?").whisper, "")

    def test_an_empty_sighting_is_falsy(self):
        self.assertFalse(Sighting())


class TestThePictureReachesTheProvider(unittest.TestCase):
    def test_the_image_is_carried_on_the_prompt(self):
        model = _Model(_reply())
        look(model, IMAGE, "Bu ne?", mime="image/png")
        self.assertEqual(model.calls[0].image, IMAGE)
        self.assertEqual(model.calls[0].image_mime, "image/png")

    def test_a_provider_that_cannot_see_still_gets_a_question(self):
        """Providers that ignore the image answer from the text, so the question has to
        stand on its own."""
        model = _Model(_reply())
        look(model, IMAGE, "Bu mantar ne?")
        self.assertIn("Bu mantar ne?", model.calls[0].user)


if __name__ == "__main__":
    unittest.main()
