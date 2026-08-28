"""Translation mode.

The one mode where silence is the wrong answer. Everything else in this engine is built
to say almost nothing; here the person cannot understand the room without it.
"""

from __future__ import annotations

import json
import unittest

from symborg_engine.copilot.translate import Rendering, Translator
from symborg_engine.providers.base import Prompt, ProviderError, VoiceRef
from symborg_engine.providers.offline import OfflineSynthesiser


def _reply(text: str, language: str = "İngilizce", literal: str = "") -> str:
    return json.dumps({"text": text, "source_language": language, "literal": literal},
                      ensure_ascii=False)


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


class _FailingVoice:
    def synthesise(self, text: str, voice: VoiceRef):
        raise ProviderError("no voice")


class TestBothDirections(unittest.TestCase):
    def test_incoming_lands_in_the_persons_language(self):
        model = _Model(_reply("Ne arıyorsunuz?"))
        rendering = Translator(model).incoming("What are you looking for?")
        self.assertEqual(rendering.text, "Ne arıyorsunuz?")
        self.assertIn("HEDEF DİL: Türkçe", model.calls[0].user)

    def test_outgoing_lands_in_the_other_language(self):
        model = _Model(_reply("Just looking, thanks."))
        rendering = Translator(model, theirs="İngilizce").outgoing("Sadece bakıyorum.",
                                                                  speak=False)
        self.assertEqual(rendering.text, "Just looking, thanks.")
        self.assertIn("HEDEF DİL: İngilizce", model.calls[0].user)

    def test_incoming_is_not_spoken_aloud(self):
        """A room with two people in it already has two voices."""
        rendering = Translator(_Model(_reply("Merhaba.")),
                               synthesiser=OfflineSynthesiser()).incoming("Hello.")
        self.assertIsNone(rendering.utterance)

    def test_outgoing_is_spoken_aloud(self):
        rendering = Translator(_Model(_reply("Hello.")),
                               synthesiser=OfflineSynthesiser()).outgoing("Merhaba.")
        self.assertIsNotNone(rendering.utterance)
        self.assertTrue(rendering.utterance.audio.startswith(b"RIFF"))

    def test_a_translation_should_not_vary_between_runs(self):
        model = _Model(_reply("x"))
        Translator(model).incoming("y")
        self.assertLessEqual(model.calls[0].temperature, 0.1)


class TestNothingIsInvented(unittest.TestCase):
    """This direction leaves the device and is heard by someone the person cannot
    check with. A failure here puts words in their mouth."""

    def test_a_provider_failure_says_nothing(self):
        self.assertFalse(Translator(_Failing()).outgoing("Merhaba", speak=False))

    def test_an_unparseable_reply_says_nothing(self):
        self.assertFalse(Translator(_Model("not json")).outgoing("Merhaba", speak=False))

    def test_an_empty_turn_is_not_sent_to_the_model(self):
        model = _Model(_reply("x"))
        self.assertFalse(Translator(model).incoming("   "))
        self.assertEqual(model.calls, [])

    def test_a_voice_failure_keeps_the_text(self):
        """Losing the audio is a degraded mode; losing the sentence is a failure. The
        text can still be shown."""
        rendering = Translator(_Model(_reply("Hello.")),
                               synthesiser=_FailingVoice()).outgoing("Merhaba.")
        self.assertEqual(rendering.text, "Hello.")
        self.assertIsNone(rendering.utterance)

    def test_the_instruction_forbids_softening(self):
        model = _Model(_reply("No."))
        Translator(model).outgoing("Hayır.", speak=False)
        system = model.calls[0].system
        self.assertIn("EKLEME YAPMA", system)
        self.assertIn("ÇIKARMA", system)


class TestRendering(unittest.TestCase):
    def test_an_empty_rendering_is_falsy(self):
        self.assertFalse(Rendering(""))
        self.assertFalse(Rendering("   "))
        self.assertTrue(Rendering("bir şey"))

    def test_whitespace_is_collapsed(self):
        rendering = Translator(_Model(_reply("iki   satır\n  bir"))).incoming("x")
        self.assertEqual(rendering.text, "iki satır bir")

    def test_a_literal_gloss_survives(self):
        rendering = Translator(_Model(_reply("Safe travels.", literal="yolun açık olsun"))
                               ).outgoing("Yolun açık olsun.", speak=False)
        self.assertEqual(rendering.literal, "yolun açık olsun")


if __name__ == "__main__":
    unittest.main()
