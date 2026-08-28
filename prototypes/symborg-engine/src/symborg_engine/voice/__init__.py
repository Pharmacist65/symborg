"""Voice banking: recording a person's voice while they can still give it."""

from __future__ import annotations

from .bank import ENROLMENT_SCRIPT, MIN_CLIP_SECONDS, TARGET_SECONDS, VoiceBank
from .consent import CONSENT_TERMS, Consent, ConsentError

__all__ = ["VoiceBank", "Consent", "ConsentError", "CONSENT_TERMS",
           "ENROLMENT_SCRIPT", "MIN_CLIP_SECONDS", "TARGET_SECONDS"]
