"""The authorship lock.

SYMBORG generates sentences for a person who, by definition, may be unable to
contradict it. The single invariant that makes that acceptable:

    Nothing is ever spoken that the person did not explicitly select.

This module is the only place that invariant lives. Synthesis takes a
``SpeechAuthorization``; it never takes raw text. A token can only be minted by
:meth:`Session.select`, is bound to one candidate from one offer, is single-use, and
expires. There is deliberately no public constructor that produces a valid token.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from hashlib import sha256

from .candidate import Candidate, Offer

__all__ = [
    "SpeechAuthorization",
    "AuthorizationError",
    "AuthorizationLedger",
    "DEFAULT_TTL_MS",
]

DEFAULT_TTL_MS = 60_000
"""How long a selection stays valid. A person may take time to confirm, but a token
found lying around minutes later should not still be able to speak."""


class AuthorizationError(RuntimeError):
    """Raised when speech is attempted without a valid, unused authorisation."""


@dataclass(slots=True, frozen=True)
class SpeechAuthorization:
    """Proof that a specific person selected a specific sentence.

    Instances are only meaningful when minted by an :class:`AuthorizationLedger`; a
    hand-constructed token will not verify, because its signature will not match the
    ledger's secret.
    """

    text: str
    candidate_id: str
    offer_id: str
    issued_at_ms: int
    ttl_ms: int
    nonce: str
    signature: str

    def is_expired(self, now_ms: int | None = None) -> bool:
        now = _now_ms() if now_ms is None else now_ms
        return now - self.issued_at_ms > self.ttl_ms


def _now_ms() -> int:
    return int(time.time() * 1000)


class AuthorizationLedger:
    """Mints and verifies speech authorisations, and records every utterance.

    One ledger per session. The secret never leaves the process; it exists so that a
    token cannot be fabricated by constructing the dataclass directly.
    """

    def __init__(self, ttl_ms: int = DEFAULT_TTL_MS) -> None:
        self._secret = secrets.token_bytes(32)
        self._ttl_ms = ttl_ms
        self._spent: set[str] = set()
        self._log: list[dict] = []

    # -- minting ---------------------------------------------------------------

    def authorise(self, offer: Offer, index: int, *, now_ms: int | None = None) -> SpeechAuthorization:
        """Mint a token for the person's selection.

        Raises:
            AuthorizationError: if the offer was already consumed, or the index does
                not correspond to a candidate that was actually offered.
        """
        if offer.consumed:
            raise AuthorizationError("offer_already_consumed")

        candidate = offer.get(index)
        if candidate is None:
            raise AuthorizationError("index_not_offered")

        issued = _now_ms() if now_ms is None else now_ms
        nonce = secrets.token_hex(16)
        token = SpeechAuthorization(
            text=candidate.text,
            candidate_id=candidate.candidate_id,
            offer_id=offer.offer_id,
            issued_at_ms=issued,
            ttl_ms=self._ttl_ms,
            nonce=nonce,
            signature=self._sign(candidate, offer, issued, nonce),
        )
        offer.consumed = True
        return token

    # -- verification ----------------------------------------------------------

    def verify(self, token: SpeechAuthorization, *, now_ms: int | None = None) -> None:
        """Check a token, or raise. Does not mark it spent — see :meth:`redeem`."""
        if not isinstance(token, SpeechAuthorization):
            raise AuthorizationError("not_an_authorization")
        expected = self._sign_raw(token.text, token.candidate_id, token.offer_id,
                                  token.issued_at_ms, token.nonce)
        if not hmac.compare_digest(expected, token.signature):
            raise AuthorizationError("invalid_signature")
        if token.is_expired(now_ms):
            raise AuthorizationError("authorization_expired")
        if token.nonce in self._spent:
            raise AuthorizationError("authorization_already_used")

    def redeem(self, token: SpeechAuthorization, *, now_ms: int | None = None) -> str:
        """Verify a token, consume it, and return the text that may be spoken."""
        self.verify(token, now_ms=now_ms)
        self._spent.add(token.nonce)
        self._log.append({
            "text": token.text,
            "candidate_id": token.candidate_id,
            "offer_id": token.offer_id,
            "origin": "user_confirmed",
            "spoken_at_ms": _now_ms() if now_ms is None else now_ms,
        })
        return token.text

    # -- audit -----------------------------------------------------------------

    @property
    def utterances(self) -> list[dict]:
        """Everything this session has spoken, in order.

        Kept separable from generated-but-not-selected text so that after the fact it
        is always clear which words the person actually chose.
        """
        return list(self._log)

    # -- internals -------------------------------------------------------------

    def _sign(self, candidate: Candidate, offer: Offer, issued_at_ms: int, nonce: str) -> str:
        return self._sign_raw(candidate.text, candidate.candidate_id, offer.offer_id,
                              issued_at_ms, nonce)

    def _sign_raw(self, text: str, candidate_id: str, offer_id: str,
                  issued_at_ms: int, nonce: str) -> str:
        payload = "\x1f".join([text, candidate_id, offer_id, str(issued_at_ms), nonce])
        return hmac.new(self._secret, payload.encode("utf-8"), sha256).hexdigest()
