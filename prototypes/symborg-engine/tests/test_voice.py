"""Voice banking.

A banked voice is used after the person can no longer object to how. Every test here
exists because that asymmetry makes the ordinary failure modes unacceptable.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from symborg_engine.voice import ENROLMENT_SCRIPT, Consent, ConsentError, VoiceBank

SILENCE = b"\x00" * (24_000 * 2 * 3)      # three seconds


class VoiceBankTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "voice"
        self.bank = VoiceBank.open(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- consent gates everything ------------------------------------------

    def test_recording_without_consent_is_refused(self) -> None:
        """Consent obtained after the fact is not consent to what was already kept."""
        with self.assertRaises(ConsentError) as ctx:
            self.bank.add_clip(0, SILENCE)
        self.assertEqual(str(ctx.exception), "no_consent_record")

    def test_consent_requires_naming_the_person(self) -> None:
        with self.assertRaises(ConsentError):
            self.bank.grant_consent("   ")

    def test_withdrawal_deletes_the_recordings(self) -> None:
        """Withdrawal that leaves the audio on disk is not withdrawal."""
        self.bank.grant_consent("Ayşe")
        clip = self.bank.add_clip(0, SILENCE)
        self.assertTrue(Path(clip.path).exists())

        self.bank.withdraw_consent()
        self.assertFalse(Path(clip.path).exists())
        self.assertEqual(self.bank.clips, [])

    def test_a_withdrawn_voice_cannot_be_used(self) -> None:
        self.bank.grant_consent("Ayşe")
        self.bank.attach_provider_voice("test", "v-123")
        self.bank.withdraw_consent()
        with self.assertRaises(ConsentError) as ctx:
            self.bank.voice_ref()
        self.assertEqual(str(ctx.exception), "consent_withdrawn")

    def test_an_unreadable_consent_record_is_not_consent(self) -> None:
        """Failing closed is the only safe direction."""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "consent.json").write_text("{ broken", encoding="utf-8")
        self.assertIsNone(Consent.load(self.root / "consent.json"))
        with self.assertRaises(ConsentError):
            VoiceBank.open(self.root).add_clip(0, SILENCE)

    def test_the_terms_are_stored_verbatim(self) -> None:
        """The record must show what was agreed, not a pointer to terms that moved."""
        consent = self.bank.grant_consent("Ayşe")
        reloaded = Consent.load(self.root / "consent.json")
        self.assertEqual(reloaded.terms, consent.terms)
        self.assertTrue(any("silebileceğim" in t for t in reloaded.terms))

    # -- recording ---------------------------------------------------------

    def test_a_clip_is_written_as_a_readable_wav(self) -> None:
        import wave
        self.bank.grant_consent("Ayşe")
        clip = self.bank.add_clip(0, SILENCE)
        with wave.open(clip.path) as handle:
            self.assertEqual(handle.getnchannels(), 1)
            self.assertEqual(handle.getframerate(), 24_000)

    def test_a_clip_that_is_too_short_is_rejected(self) -> None:
        self.bank.grant_consent("Ayşe")
        with self.assertRaises(ValueError):
            self.bank.add_clip(0, b"\x00" * 1000)

    def test_rerecording_replaces_rather_than_duplicates(self) -> None:
        self.bank.grant_consent("Ayşe")
        self.bank.add_clip(0, SILENCE)
        self.bank.add_clip(0, SILENCE)
        self.assertEqual(len(self.bank.clips), 1)

    def test_progress_survives_reopening(self) -> None:
        self.bank.grant_consent("Ayşe")
        self.bank.add_clip(0, SILENCE)
        self.bank.add_clip(1, SILENCE)
        reopened = VoiceBank.open(self.root)
        self.assertEqual(len(reopened.clips), 2)
        self.assertEqual(reopened.consent.person, "Ayşe")

    # -- the script --------------------------------------------------------

    def test_everyday_phrases_come_first(self) -> None:
        """Enrolment is tiring and people stop early, so the sentences most needed
        later must be captured first."""
        head = " ".join(ENROLMENT_SCRIPT[:10])
        for essential in ("Evet", "Hayır", "Seni seviyorum", "Ağrım var"):
            self.assertIn(essential, head)

    def test_next_prompt_advances_and_ends(self) -> None:
        self.bank.grant_consent("Ayşe")
        self.assertEqual(self.bank.next_prompt[0], 0)
        for i in range(len(ENROLMENT_SCRIPT)):
            self.bank.add_clip(i, SILENCE)
        self.assertIsNone(self.bank.next_prompt)

    # -- the voice ---------------------------------------------------------

    def test_a_voice_needs_a_provider_before_it_can_be_used(self) -> None:
        self.bank.grant_consent("Ayşe")
        with self.assertRaises(ConsentError) as ctx:
            self.bank.voice_ref()
        self.assertEqual(str(ctx.exception), "no_voice_attached")

    def test_the_voice_is_marked_as_the_persons_own(self) -> None:
        self.bank.grant_consent("Ayşe")
        self.bank.attach_provider_voice("test", "v-123")
        ref = self.bank.voice_ref()
        self.assertTrue(ref.is_own_voice)
        self.assertEqual(ref.label, "Ayşe")

    def test_readiness_needs_real_material(self) -> None:
        self.bank.grant_consent("Ayşe")
        self.assertFalse(self.bank.is_ready)
        for i in range(len(ENROLMENT_SCRIPT)):
            self.bank.add_clip(i, SILENCE)
        self.assertTrue(self.bank.is_ready)


if __name__ == "__main__":
    unittest.main()
