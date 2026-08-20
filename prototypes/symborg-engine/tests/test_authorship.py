"""The authorship invariant.

If any test in this file fails, the product is unsafe: it means the engine can speak
words the person did not choose. These are written adversarially on purpose.
"""

from __future__ import annotations

import unittest

from symborg_engine import AuthorizationError, Session
from symborg_engine.authorship import AuthorizationLedger, SpeechAuthorization
from symborg_engine.candidate import Candidate, Offer


class TestSpeechRequiresSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session()
        self.session.hear("Ağrın var mı?")

    def test_speak_rejects_raw_text(self) -> None:
        """speak() must not accept a string. Text is not authorisation."""
        with self.assertRaises(AuthorizationError):
            self.session.speak("Evet, ağrım var.")  # type: ignore[arg-type]

    def test_speak_rejects_forged_token(self) -> None:
        """A hand-constructed token must not verify: the signature cannot be guessed."""
        self.session.offer()
        forged = SpeechAuthorization(
            text="Beni hastaneye götürün.",
            candidate_id="x", offer_id="y",
            issued_at_ms=10_000, ttl_ms=60_000,
            nonce="deadbeef", signature="0" * 64,
        )
        with self.assertRaises(AuthorizationError) as ctx:
            self.session.speak(forged)
        self.assertEqual(str(ctx.exception), "invalid_signature")

    def test_select_without_offer_fails(self) -> None:
        with self.assertRaises(AuthorizationError) as ctx:
            self.session.select(0)
        self.assertEqual(str(ctx.exception), "no_active_offer")

    def test_select_index_never_offered_fails(self) -> None:
        result = self.session.offer()
        with self.assertRaises(AuthorizationError) as ctx:
            self.session.select(len(result.candidates) + 5)
        self.assertEqual(str(ctx.exception), "index_not_offered")

    def test_negative_index_fails(self) -> None:
        """Negative indices must not wrap around to a different candidate."""
        self.session.offer()
        with self.assertRaises(AuthorizationError):
            self.session.select(-1)

    def test_token_is_single_use(self) -> None:
        self.session.offer()
        token = self.session.select(0)
        self.session.speak(token)
        with self.assertRaises(AuthorizationError) as ctx:
            self.session.speak(token)
        self.assertEqual(str(ctx.exception), "authorization_already_used")

    def test_offer_cannot_be_selected_twice(self) -> None:
        """One offer authorises one sentence, not two."""
        self.session.offer()
        self.session.select(0)
        with self.assertRaises(AuthorizationError):
            self.session.select(1)

    def test_expired_token_fails(self) -> None:
        ledger = AuthorizationLedger(ttl_ms=1_000)
        offer = Offer(candidates=(Candidate(text="Evet."),))
        token = ledger.authorise(offer, 0, now_ms=0)
        with self.assertRaises(AuthorizationError) as ctx:
            ledger.verify(token, now_ms=5_000)
        self.assertEqual(str(ctx.exception), "authorization_expired")

    def test_token_from_another_session_fails(self) -> None:
        """Tokens are session-scoped: one person's selection cannot speak elsewhere."""
        other = Session()
        other.hear("Nasılsın?")
        other.offer()
        foreign = other.select(0)
        self.session.offer()
        with self.assertRaises(AuthorizationError) as ctx:
            self.session.speak(foreign)
        self.assertEqual(str(ctx.exception), "invalid_signature")

    def test_token_text_cannot_be_swapped(self) -> None:
        """Changing the text after minting must invalidate the signature."""
        self.session.offer()
        token = self.session.select(0)
        tampered = SpeechAuthorization(
            text="Fişimi çekin.",
            candidate_id=token.candidate_id, offer_id=token.offer_id,
            issued_at_ms=token.issued_at_ms, ttl_ms=token.ttl_ms,
            nonce=token.nonce, signature=token.signature,
        )
        with self.assertRaises(AuthorizationError):
            self.session.speak(tampered)

    def test_rejected_offer_cannot_speak(self) -> None:
        self.session.offer()
        self.session.reject("hiçbiri değil")
        with self.assertRaises(AuthorizationError):
            self.session.select(0)

    def test_spoken_text_matches_selection_exactly(self) -> None:
        result = self.session.offer()
        chosen = result.candidates[1]
        token = self.session.select(1)
        spoken = self.session.speak(token)
        self.assertEqual(spoken.utterance.text, chosen.text)

    def test_every_utterance_is_logged_as_user_confirmed(self) -> None:
        self.session.offer()
        self.session.speak(self.session.select(0))
        log = self.session.spoken
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["origin"], "user_confirmed")

    def test_generated_but_unselected_text_is_never_spoken(self) -> None:
        result = self.session.offer()
        self.session.speak(self.session.select(0))
        spoken_texts = {entry["text"] for entry in self.session.spoken}
        unselected = {c.text for c in result.candidates[1:]}
        self.assertFalse(spoken_texts & unselected)


if __name__ == "__main__":
    unittest.main()
