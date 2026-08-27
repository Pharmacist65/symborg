"""Candidate generation, parsing and filtering."""

from __future__ import annotations

import unittest

from symborg_engine import Candidate, ProviderError, Session, Transcript, Vault
from symborg_engine.generate.candidates import (
    dedupe, expand_abbreviation, generate_candidates, parse_candidates,
)
from symborg_engine.providers.base import Prompt


class _FixedModel:
    """A language model returning a canned response."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[Prompt] = []

    def complete(self, prompt: Prompt) -> str:
        self.calls.append(prompt)
        return self.response


class _FailingModel:
    def complete(self, prompt: Prompt) -> str:
        raise ProviderError("provider_down")


class TestParsing(unittest.TestCase):
    def test_parses_plain_json(self) -> None:
        out = parse_candidates('[{"text": "Evet.", "kind": "reply", "confidence": 0.9}]')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].text, "Evet.")

    def test_parses_json_in_code_fence(self) -> None:
        out = parse_candidates('```json\n[{"text": "Evet.", "kind": "reply"}]\n```')
        self.assertEqual(len(out), 1)

    def test_parses_json_surrounded_by_prose(self) -> None:
        out = parse_candidates('İşte adaylar:\n[{"text": "Evet."}]\nUmarım yardımcı olur.')
        self.assertEqual(len(out), 1)

    def test_malformed_json_yields_nothing(self) -> None:
        """A parse failure must not become an invented sentence."""
        self.assertEqual(parse_candidates("not json at all"), [])
        self.assertEqual(parse_candidates('[{"text": '), [])

    def test_unknown_kind_falls_back_to_reply(self) -> None:
        out = parse_candidates('[{"text": "Evet.", "kind": "telepathy"}]')
        self.assertEqual(out[0].kind, "reply")

    def test_empty_text_is_dropped(self) -> None:
        self.assertEqual(parse_candidates('[{"text": "   "}]'), [])


class TestFiltering(unittest.TestCase):
    def test_dedupe_removes_near_duplicates(self) -> None:
        cands = [
            Candidate(text="Sırtım çok ağrıyor."),
            Candidate(text="Çok ağrıyor sırtım."),
            Candidate(text="Su içmek istiyorum."),
        ]
        self.assertEqual(len(dedupe(cands)), 2)

    def test_overlong_candidates_are_rejected(self) -> None:
        long_text = " ".join(["kelime"] * 40)
        model = _FixedModel(f'[{{"text": "{long_text}", "confidence": 0.9}}]')
        out = generate_candidates(model, Transcript())
        self.assertEqual(out, [])

    def test_clinical_assertions_are_filtered(self) -> None:
        """The system may not put a diagnosis or a dose in the person's mouth."""
        model = _FixedModel(
            '[{"text": "Doktor bana kanser teşhisi koydu.", "confidence": 0.9},'
            ' {"text": "İlacımın dozunu artırın.", "confidence": 0.8},'
            ' {"text": "Bugün kendimi iyi hissetmiyorum.", "confidence": 0.7}]'
        )
        out = generate_candidates(model, Transcript())
        texts = [c.text for c in out]
        self.assertIn("Bugün kendimi iyi hissetmiyorum.", texts)
        self.assertEqual(len(out), 1)

    def test_first_person_symptom_report_is_allowed(self) -> None:
        """Reporting one's own symptom is the person's own speech, not a diagnosis."""
        model = _FixedModel('[{"text": "Belim ağrıyor.", "confidence": 0.9}]')
        out = generate_candidates(model, Transcript())
        self.assertEqual(len(out), 1)

    def test_provider_failure_yields_no_candidates(self) -> None:
        self.assertEqual(generate_candidates(_FailingModel(), Transcript()), [])


class TestExpansion(unittest.TestCase):
    def test_expansion_returns_candidates(self) -> None:
        model = _FixedModel('[{"text": "Su içmek istiyorum.", "confidence": 0.9}]')
        out = expand_abbreviation(model, "su ist", Transcript())
        self.assertEqual(out[0].text, "Su içmek istiyorum.")

    def test_expansion_failure_returns_input_unchanged(self) -> None:
        """A failed expansion must not replace the person's input with a guess."""
        out = expand_abbreviation(_FailingModel(), "su ist", Transcript())
        self.assertEqual(out[0].text, "su ist")

    def test_empty_abbreviation_yields_nothing(self) -> None:
        self.assertEqual(expand_abbreviation(_FixedModel("[]"), "   ", Transcript()), [])

    def test_expansion_still_requires_selection(self) -> None:
        """Expansion is not a bypass around authorship."""
        session = Session()
        session.hear("Ne istiyorsun?")
        session.offer_expansion("su ist")
        self.assertTrue(session.spoken == [])


class TestPromptContent(unittest.TestCase):
    def test_vault_context_reaches_the_prompt(self) -> None:
        vault = Vault(display_name="Ayşe", relationships={"Deniz": "kızı"})
        model = _FixedModel("[]")
        generate_candidates(model, Transcript(), vault)
        self.assertIn("Ayşe", model.calls[0].user)
        self.assertIn("Deniz", model.calls[0].user)

    def test_transcript_reaches_the_prompt(self) -> None:
        transcript = Transcript()
        transcript.add_text("Ağrın var mı?")
        model = _FixedModel("[]")
        generate_candidates(model, transcript)
        self.assertIn("Ağrın var mı?", model.calls[0].user)


if __name__ == "__main__":
    unittest.main()


class TestTurkishMorphology(unittest.TestCase):
    """Turkish is agglutinative and has two i/I pairs.

    Both broke a first version of the clinical filter, so both are pinned here.
    """

    def _rejected(self, text: str) -> bool:
        model = _FixedModel(f'[{{"text": "{text}", "confidence": 0.9}}]')
        return generate_candidates(model, Transcript()) == []

    def test_suffixed_forms_are_still_caught(self) -> None:
        for text in [
            "İlacımın dozunu artırın.",
            "Dozumu azaltmalıyız.",
            "İlacımı kesin.",
        ]:
            with self.subTest(text=text):
                self.assertTrue(self._rejected(text))

    def test_dotted_capital_i_is_folded(self) -> None:
        """'İ' must fold to 'i'; str.lower() alone produces a combining dot."""
        self.assertTrue(self._rejected("İlacımı bırakın."))

    def test_ordinary_first_person_speech_survives(self) -> None:
        for text in [
            "Belim ağrıyor.",
            "Işıklar gözümü alıyor.",
            "İyi hissetmiyorum.",
            "Su içmek istiyorum.",
        ]:
            with self.subTest(text=text):
                self.assertFalse(self._rejected(text))


class TestStructuredOutputShapes(unittest.TestCase):
    """Providers that constrain decoding must wrap the array in an object.

    Both shapes have to parse, or the engine would depend on which vendor answered.
    """

    def test_object_wrapper_is_unwrapped(self) -> None:
        out = parse_candidates('{"candidates": [{"text": "Evet.", "kind": "reply", "confidence": 0.8}]}')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].text, "Evet.")

    def test_bare_array_still_parses(self) -> None:
        self.assertEqual(len(parse_candidates('[{"text": "Evet."}]')), 1)

    def test_object_without_a_list_yields_nothing(self) -> None:
        self.assertEqual(parse_candidates('{"error": "nope"}'), [])

    def test_schema_is_offered_to_the_provider(self) -> None:
        model = _FixedModel("[]")
        generate_candidates(model, Transcript())
        schema = model.calls[0].json_schema
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertIn("candidates", schema["properties"])
