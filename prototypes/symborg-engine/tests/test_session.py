"""Session flow, context handling and offline behaviour."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from symborg_engine import Session, Transcript, Vault
from symborg_engine.providers import resolve_language_model
from symborg_engine.providers.offline import (
    OfflineLanguageModel, OfflineSynthesiser, OfflineTranscriber,
)
from symborg_engine.providers.base import Prompt, VoiceRef


class TestOfflineByDefault(unittest.TestCase):
    def test_session_constructs_with_no_arguments(self) -> None:
        """A contributor with no key must be able to run the engine immediately."""
        session = Session()
        session.hear("Nasılsın?")
        result = session.offer()
        self.assertGreater(len(result.candidates), 0)

    def test_full_loop_offline(self) -> None:
        session = Session()
        session.hear("Ağrın var mı?")
        result = session.offer()
        spoken = session.speak(session.select(0))
        self.assertEqual(spoken.utterance.text, result.candidates[0].text)
        self.assertTrue(spoken.utterance.audio.startswith(b"RIFF"))

    def test_offline_model_is_deterministic(self) -> None:
        """Tests are only meaningful if the offline provider does not drift."""
        model = OfflineLanguageModel()
        prompt = Prompt(system="s", user="Partner: Ağrın var mı?")
        self.assertEqual(model.complete(prompt), model.complete(prompt))

    def test_offline_output_parses_like_a_real_response(self) -> None:
        """The offline path must not be a special case in the engine."""
        raw = OfflineLanguageModel().complete(Prompt(system="s", user="Partner: Ağrın var mı?"))
        payload = json.loads(raw)
        self.assertIsInstance(payload, list)
        self.assertIn("text", payload[0])

    def test_resolve_falls_back_to_offline(self) -> None:
        import os
        previous = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            self.assertIsInstance(resolve_language_model(), OfflineLanguageModel)
        finally:
            if previous is not None:
                os.environ["ANTHROPIC_API_KEY"] = previous

    def test_offline_synthesiser_emits_valid_wav(self) -> None:
        utterance = OfflineSynthesiser().synthesise("Merhaba", VoiceRef(voice_id="v1"))
        self.assertTrue(utterance.audio.startswith(b"RIFF"))
        self.assertIn(b"WAVE", utterance.audio[:16])
        self.assertEqual(utterance.voice_id, "v1")

    def test_offline_transcriber_returns_final_chunk(self) -> None:
        chunk = OfflineTranscriber().transcribe(b"\x00\x01")
        self.assertTrue(chunk.is_final)


class TestTranscript(unittest.TestCase):
    def test_window_is_bounded(self) -> None:
        transcript = Transcript(window_turns=3)
        for i in range(10):
            transcript.add_text(f"satır {i}")
        self.assertEqual(len(transcript.chunks), 3)

    def test_interim_chunks_are_ignored(self) -> None:
        """Acting on text still being revised produces candidates for nothing said."""
        from symborg_engine import TranscriptChunk
        transcript = Transcript()
        transcript.add(TranscriptChunk(text="yarım cüm", is_final=False))
        self.assertTrue(transcript.is_empty())

    def test_render_labels_speakers(self) -> None:
        transcript = Transcript()
        transcript.add_text("Ağrın var mı?", speaker="partner")
        transcript.add_text("Evet.", speaker="user")
        rendered = transcript.render()
        self.assertIn("Partner: Ağrın var mı?", rendered)
        self.assertIn("Kullanıcı: Evet.", rendered)

    def test_spoken_sentence_enters_the_transcript(self) -> None:
        session = Session()
        session.hear("Ağrın var mı?")
        session.offer()
        spoken = session.speak(session.select(0))
        self.assertIn(spoken.utterance.text, session.transcript.render())


class TestVault(unittest.TestCase):
    def test_roundtrip(self) -> None:
        vault = Vault(display_name="Ayşe", recurring_needs=["pozisyon değişimi"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vault.json"
            vault.save(path)
            loaded = Vault.load(path)
        self.assertEqual(loaded.display_name, "Ayşe")
        self.assertEqual(loaded.recurring_needs, ["pozisyon değişimi"])

    def test_missing_file_yields_empty_vault(self) -> None:
        self.assertTrue(Vault.load("/nonexistent/path/vault.json").is_empty())

    def test_corrupt_file_does_not_raise(self) -> None:
        """A corrupt vault must not stop someone communicating."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vault.json"
            path.write_text("{ this is not json", encoding="utf-8")
            self.assertTrue(Vault.load(path).is_empty())

    def test_accepted_utterances_are_capped(self) -> None:
        vault = Vault()
        for i in range(Vault.MAX_ACCEPTED + 20):
            vault.remember_accepted(f"cümle {i}")
        self.assertEqual(len(vault.accepted_utterances), Vault.MAX_ACCEPTED)

    def test_selection_is_remembered(self) -> None:
        session = Session()
        session.hear("Ağrın var mı?")
        session.offer()
        spoken = session.speak(session.select(0))
        self.assertIn(spoken.utterance.text, session.vault.accepted_utterances)


class TestSilenceIsValid(unittest.TestCase):
    def test_empty_offer_is_marked_degraded_not_faked(self) -> None:
        class _Empty:
            def complete(self, prompt: Prompt) -> str:
                return "[]"

        session = Session(model=_Empty())
        result = session.offer()
        self.assertTrue(result.is_empty)
        self.assertTrue(result.degraded)

    def test_latency_is_reported(self) -> None:
        session = Session()
        session.hear("Merhaba")
        self.assertGreaterEqual(session.offer().latency_ms, 0)


if __name__ == "__main__":
    unittest.main()
