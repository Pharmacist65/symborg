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


class ConsentRecordingTest(unittest.TestCase):
    """A tick box cannot be verified once the person can no longer confirm it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "voice"
        self.bank = VoiceBank.open(self.root)
        self.rec = Path(self._tmp.name) / "consent.wav"
        self.rec.write_bytes(b"RIFF" + b"\x00" * 2000)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_recording_is_fingerprinted(self) -> None:
        consent = self.bank.grant_consent("Ayşe", recording=self.rec)
        self.assertTrue(consent.recording_sha256)
        self.assertTrue(consent.recording_is_intact)
        self.assertTrue(consent.is_verifiable)

    def test_a_tampered_recording_stops_verifying(self) -> None:
        """The record must show it is no longer the audio that was agreed to."""
        consent = self.bank.grant_consent("Ayşe", recording=self.rec)
        self.rec.write_bytes(b"RIFF" + b"\xff" * 2000)
        self.assertFalse(consent.recording_is_intact)
        self.assertFalse(consent.is_verifiable)

    def test_a_missing_recording_is_refused(self) -> None:
        """A record pointing at nothing is worse than one admitting it has none."""
        with self.assertRaises(ConsentError):
            self.bank.grant_consent("Ayşe", recording=self.root / "nope.wav")

    def test_consent_without_a_recording_is_valid_but_not_verifiable(self) -> None:
        consent = self.bank.grant_consent("Ayşe")
        self.assertTrue(consent.is_valid)
        self.assertFalse(consent.is_verifiable)


class ConsentScopeTest(unittest.TestCase):
    """Scope is checked, not hoped for."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.bank = VoiceBank.open(Path(self._tmp.name) / "voice")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cloud_synthesis_can_be_refused(self) -> None:
        from symborg_engine.voice import ConsentScope
        self.bank.grant_consent("Ayşe", scope=ConsentScope(allow_cloud_synthesis=False))
        self.bank.attach_provider_voice("test", "v-1")
        with self.assertRaises(ConsentError) as ctx:
            self.bank.voice_ref(cloud_synthesis=True)
        self.assertEqual(str(ctx.exception), "cloud_synthesis_not_consented")
        self.bank.voice_ref(cloud_synthesis=False)      # on-device is still fine

    def test_proxy_selection_is_off_unless_agreed(self) -> None:
        consent = self.bank.grant_consent("Ayşe")
        with self.assertRaises(ConsentError) as ctx:
            consent.require_valid(proxy_selection=True)
        self.assertEqual(str(ctx.exception), "proxy_selection_not_consented")

    def test_a_device_outside_the_record_is_refused(self) -> None:
        from symborg_engine.voice import ConsentScope
        self.bank.grant_consent("Ayşe", scope=ConsentScope(devices=("tablet-1",)))
        self.bank.attach_provider_voice("test", "v-1")
        self.bank.voice_ref(device="tablet-1")
        with self.assertRaises(ConsentError):
            self.bank.voice_ref(device="someone-elses-phone")

    def test_scope_survives_reopening(self) -> None:
        from symborg_engine.voice import ConsentScope
        root = self.bank.root
        self.bank.grant_consent("Ayşe", scope=ConsentScope(allow_cloud_synthesis=False))
        reopened = VoiceBank.open(root)
        self.assertFalse(reopened.consent.scope.allow_cloud_synthesis)


class WithdrawalPropagationTest(unittest.TestCase):
    """Withdrawal that stops at this machine is not withdrawal.

    The clone keeps working wherever it was trained, so "delete my voice" would delete
    nothing that matters.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "voice"
        self.bank = VoiceBank.open(self.root)
        self.bank.grant_consent("Ayşe")
        self.bank.add_clip(0, SILENCE)
        self.bank.attach_provider_voice("elevenlabs", "v-remote-1")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_deletion_reaches_the_provider(self) -> None:
        called: list[tuple[str, str]] = []

        def delete(provider: str, voice_id: str) -> bool:
            called.append((provider, voice_id))
            return True

        outcome = self.bank.withdraw_consent(delete_remote=delete)
        self.assertEqual(called, [("elevenlabs", "v-remote-1")])
        self.assertTrue(outcome["remote_deleted"])
        self.assertTrue(self.bank.consent.withdrawal_propagated)

    def test_without_a_handler_propagation_is_not_claimed(self) -> None:
        outcome = self.bank.withdraw_consent()
        self.assertFalse(outcome["remote_deleted"])
        self.assertEqual(outcome["remote_error"], "no_deletion_handler")
        self.assertFalse(self.bank.consent.withdrawal_propagated)

    def test_a_failing_provider_is_reported_not_hidden(self) -> None:
        def delete(provider: str, voice_id: str) -> bool:
            raise RuntimeError("service unreachable")

        outcome = self.bank.withdraw_consent(delete_remote=delete)
        self.assertIn("service unreachable", outcome["remote_error"])
        self.assertFalse(self.bank.consent.withdrawal_propagated)

    def test_local_audio_goes_even_when_the_provider_fails(self) -> None:
        """The part that can be honoured must be honoured."""
        clip = Path(self.bank.clips[0].path)
        self.bank.withdraw_consent(delete_remote=lambda p, v: False)
        self.assertFalse(clip.exists())

    def test_nothing_remote_counts_as_fully_propagated(self) -> None:
        bank = VoiceBank.open(Path(self._tmp.name) / "voice2")
        bank.grant_consent("Mehmet")
        bank.withdraw_consent()
        self.assertTrue(bank.consent.withdrawal_propagated)


class JournalTest(unittest.TestCase):
    """What was said in this person's name has to outlive the session."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "spoken.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _session(self):
        from symborg_engine import Session
        from symborg_engine.providers.base import Prompt

        class _Model:
            def complete(self, prompt: Prompt) -> str:
                return '[{"text": "Evet.", "kind": "reply", "confidence": 0.9}]'

        return Session(model=_Model(), journal=str(self.path), consent_id="c-123")

    def test_an_utterance_survives_the_session(self) -> None:
        from symborg_engine.authorship import AuthorizationLedger

        session = self._session()
        session.hear("Ağrın var mı?")
        session.offer()
        session.speak(session.select(0))
        del session

        entries = AuthorizationLedger.read_journal(self.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "Evet.")
        self.assertEqual(entries[0]["origin"], "user_confirmed")

    def test_every_entry_names_the_consent_it_spoke_under(self) -> None:
        from symborg_engine.authorship import AuthorizationLedger

        session = self._session()
        session.hear("Ağrın var mı?")
        session.offer()
        session.speak(session.select(0))
        self.assertEqual(AuthorizationLedger.read_journal(self.path)[0]["consent_id"], "c-123")

    def test_sessions_accumulate_rather_than_overwrite(self) -> None:
        from symborg_engine.authorship import AuthorizationLedger

        for _ in range(3):
            session = self._session()
            session.hear("Ağrın var mı?")
            session.offer()
            session.speak(session.select(0))
        self.assertEqual(len(AuthorizationLedger.read_journal(self.path)), 3)

    def test_a_corrupt_line_does_not_hide_the_rest(self) -> None:
        from symborg_engine.authorship import AuthorizationLedger

        self.path.write_text('{"text": "bir"}\nnot json\n{"text": "iki"}\n', encoding="utf-8")
        entries = AuthorizationLedger.read_journal(self.path)
        self.assertEqual([e["text"] for e in entries], ["bir", "iki"])

    def test_an_unwritable_journal_does_not_stop_someone_speaking(self) -> None:
        from symborg_engine import Session
        from symborg_engine.providers.base import Prompt

        class _Model:
            def complete(self, prompt: Prompt) -> str:
                return '[{"text": "Evet.", "kind": "reply", "confidence": 0.9}]'

        session = Session(model=_Model(), journal="/nonexistent-root/x/spoken.jsonl")
        session.hear("Ağrın var mı?")
        session.offer()
        spoken = session.speak(session.select(0))       # must not raise
        self.assertEqual(spoken.utterance.text, "Evet.")
        self.assertEqual(len(session.spoken), 1)        # still kept in memory
