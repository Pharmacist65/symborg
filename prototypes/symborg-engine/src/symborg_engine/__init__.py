"""SYMBORG assist engine.

A communication aid for people who cannot speak: it reads the conversation, offers a
few complete sentences, and speaks the one the person selects — in their own banked
voice.

The engine never speaks anything the person did not explicitly select. That invariant
lives in :mod:`symborg_engine.authorship` and is enforced by the type of the argument
:meth:`Session.speak` accepts.

    >>> from symborg_engine import Session
    >>> session = Session()                 # works offline, no key required
    >>> session.hear("Ağrın var mı?")
    >>> result = session.offer()
    >>> token = session.select(0)           # the person chooses
    >>> spoken = session.speak(token)

This is research software. It is not a medical device, it does not diagnose or treat,
and it makes no clinical claims.
"""

from __future__ import annotations

from .authorship import AuthorizationError, AuthorizationLedger, SpeechAuthorization
from .candidate import Candidate, Offer
from .context.transcript import Transcript
from .context.vault import Vault
from .providers.base import (
    LanguageModel, Prompt, ProviderError, Synthesiser, Transcriber,
    TranscriptChunk, Utterance, VoiceRef,
)
from .session import OfferResult, Session, SpeakResult
from .stream import Fragment, TextStream, TranscriptStream, TurnResult, drive
from .turntaking import TurnMonitor, TurnSignal, completion_score

__version__ = "0.1.0"

__all__ = [
    "Session", "OfferResult", "SpeakResult",
    "drive", "Fragment", "TextStream", "TranscriptStream", "TurnResult",
    "TurnMonitor", "TurnSignal", "completion_score",
    "Candidate", "Offer",
    "SpeechAuthorization", "AuthorizationError", "AuthorizationLedger",
    "Transcript", "Vault",
    "LanguageModel", "Synthesiser", "Transcriber",
    "Prompt", "ProviderError", "TranscriptChunk", "Utterance", "VoiceRef",
    "__version__",
]
