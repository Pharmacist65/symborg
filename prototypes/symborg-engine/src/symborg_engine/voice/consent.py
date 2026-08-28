"""Consent for banking a voice.

A banked voice outlives the moment it was given. It will be used after the person can
no longer speak — which is the entire point, and also the reason consent cannot be a
checkbox. By the time the voice is used, the person may be unable to object to how.

So consent is a record, not a flag: who gave it, when, in what words, and what they
agreed to. It travels with the recordings, and the engine refuses to use a voice whose
consent record is missing or has been withdrawn.

This is not legal advice and does not replace whatever a clinical or regulatory context
requires. It is the minimum a system should keep in order to be able to answer, later,
the question: who said this may be done.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = ["Consent", "ConsentError", "CONSENT_TERMS"]

CONSENT_TERMS: tuple[str, ...] = (
    "Bu ses kaydı yalnızca benim adıma konuşmak için kullanılacak.",
    "Ses kaydım cihazımda saklanacak ve istediğim zaman silebileceğim.",
    "Hiçbir cümle, ben ya da benim adıma karar vermeye yetkili biri seçmeden söylenmeyecek.",
    "Bu iznimi istediğim zaman geri alabilirim; geri aldığımda sesim kullanılamaz.",
    "Bu bir tıbbi cihaz değildir ve tedavi amaçlı değildir.",
)
"""What the person is agreeing to, in their own language.

Kept as text rather than a version number so that the record shows what was actually
agreed, not a pointer to terms that may since have changed."""


class ConsentError(RuntimeError):
    """Raised when a voice is used without valid consent."""


@dataclass(slots=True)
class Consent:
    """A record that a person agreed their voice may be reproduced."""

    person: str
    """Who the voice belongs to."""
    granted_by: str = ""
    """Who gave the consent, if not the person themselves — a legal representative.
    Left empty for self-consent, which is the only case this prototype supports."""
    terms: tuple[str, ...] = CONSENT_TERMS
    granted_at_ms: int = 0
    withdrawn_at_ms: int = 0
    note: str = ""
    consent_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.granted_at_ms == 0:
            self.granted_at_ms = int(time.time() * 1000)
        self.terms = tuple(self.terms)

    @property
    def is_valid(self) -> bool:
        return bool(self.person) and self.withdrawn_at_ms == 0

    def withdraw(self) -> None:
        """Revoke consent. The voice becomes unusable immediately."""
        if self.withdrawn_at_ms == 0:
            self.withdrawn_at_ms = int(time.time() * 1000)

    def require_valid(self) -> None:
        if not self.person:
            raise ConsentError("no_person_named")
        if self.withdrawn_at_ms:
            raise ConsentError("consent_withdrawn")

    # -- persistence -----------------------------------------------------------

    def to_dict(self) -> dict:
        data = asdict(self)
        data["terms"] = list(self.terms)
        return data

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Consent | None":
        p = Path(path)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A consent record that cannot be read is not consent. Failing closed is
            # the only safe direction here.
            return None
        known = {f for f in cls.__slots__ if not f.startswith("_")}
        return cls(**{k: v for k, v in data.items() if k in known})
