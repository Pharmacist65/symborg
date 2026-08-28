"""Consent for banking a voice.

A banked voice outlives the moment it was given. It is used after the person can no
longer speak — which is the point, and also why consent here cannot be a checkbox. By
the time the voice is used, the person may be unable to object to how.

Two consequences shape this module.

**A tick box cannot be verified once the person is gone.** So consent is recorded in
their own voice, on video or audio, reading the terms aloud. The file is part of the
record and its digest is stored with it, so a later reader can tell that the recording
they are hearing is the one that was agreed to.

**Consent has a shape, not just a value.** What may be said, who may choose it, on which
device — these are fields that are checked, not prose that is hoped for.

This is not legal advice and does not replace what a clinical or regulatory context
requires. It is the minimum needed to answer, later, the question: who said this may be
done, and to what exactly.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = ["Consent", "ConsentError", "ConsentScope", "CONSENT_TERMS"]

CONSENT_TERMS: tuple[str, ...] = (
    "Bu ses kaydı yalnızca benim adıma konuşmak için kullanılacak.",
    "Ses kaydım cihazımda saklanacak ve istediğim zaman silebileceğim.",
    "Hiçbir cümle, ben ya da benim adıma karar vermeye yetkili biri seçmeden söylenmeyecek.",
    "Bu iznimi istediğim zaman geri alabilirim; geri aldığımda sesim kullanılamaz.",
    "Bu bir tıbbi cihaz değildir ve tedavi amaçlı değildir.",
)
"""What the person is agreeing to, in their own language.

Stored verbatim rather than as a version number, so the record shows what was actually
agreed rather than pointing at terms that may since have changed."""


class ConsentError(RuntimeError):
    """Raised when a voice is used without valid consent."""


@dataclass(slots=True)
class ConsentScope:
    """The limits of what was agreed, as fields that can be checked."""

    speak_selected_only: bool = True
    """Only sentences the person selected may be spoken. Turning this off is not a
    supported configuration; it exists so that a record can say it was never true."""
    allow_proxy_selection: bool = False
    """Whether someone acting for the person may select on their behalf."""
    allow_cloud_synthesis: bool = True
    """Whether the voice may be sent to a hosted service to be synthesised."""
    devices: tuple[str, ...] = ()
    """Devices this was agreed for. Empty means unrestricted."""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["devices"] = list(self.devices)
        return data


@dataclass(slots=True)
class Consent:
    """A record that a person agreed their voice may be reproduced."""

    person: str
    granted_by: str = ""
    """Who gave consent, when not the person themselves.

    Empty means self-consent, which is the strongest form and the one to prefer while
    the person can still give it. A named proxy is supported because progressive
    conditions do not wait, but it is recorded as what it is."""
    terms: tuple[str, ...] = CONSENT_TERMS
    scope: ConsentScope = field(default_factory=ConsentScope)
    recording_path: str = ""
    """Where the person is heard agreeing, in their own voice."""
    recording_sha256: str = ""
    granted_at_ms: int = 0
    withdrawn_at_ms: int = 0
    withdrawal_propagated: bool = False
    """Whether deletion reached every service holding a copy of the voice.

    Withdrawal that stops at this machine is not withdrawal: the clone keeps working
    wherever it was trained."""
    note: str = ""
    consent_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.granted_at_ms == 0:
            self.granted_at_ms = int(time.time() * 1000)
        self.terms = tuple(self.terms)
        if isinstance(self.scope, dict):
            devices = tuple(self.scope.get("devices", ()))
            self.scope = ConsentScope(**{**self.scope, "devices": devices})

    # -- the recording ---------------------------------------------------------

    def attach_recording(self, path: str | Path) -> None:
        """Attach the person reading the terms aloud, and fingerprint it.

        Raises:
            ConsentError: if the file is missing. A record that points at nothing is
                worse than one that admits it has no recording.
        """
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            raise ConsentError("recording_missing")
        digest = hashlib.sha256()
        with p.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        self.recording_path = str(p)
        self.recording_sha256 = digest.hexdigest()

    @property
    def recording_is_intact(self) -> bool:
        """Whether the attached recording is still the one that was agreed to."""
        if not self.recording_path or not self.recording_sha256:
            return False
        p = Path(self.recording_path)
        if not p.exists():
            return False
        digest = hashlib.sha256()
        with p.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest() == self.recording_sha256

    @property
    def is_verifiable(self) -> bool:
        """Whether this consent could be shown to someone else and stand up."""
        return self.is_valid and self.recording_is_intact

    # -- validity --------------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        return bool(self.person) and self.withdrawn_at_ms == 0

    def withdraw(self) -> None:
        """Mark consent revoked. Deleting the audio is the caller's job — see
        :meth:`VoiceBank.withdraw_consent`, which does both."""
        if self.withdrawn_at_ms == 0:
            self.withdrawn_at_ms = int(time.time() * 1000)

    def require_valid(self, *, proxy_selection: bool = False,
                      cloud_synthesis: bool = False, device: str = "") -> None:
        """Check consent covers what is about to happen.

        Args:
            proxy_selection: Someone is choosing on the person's behalf.
            cloud_synthesis: The voice is about to be sent to a hosted service.
            device: The device this is running on, if the record restricts them.
        """
        if not self.person:
            raise ConsentError("no_person_named")
        if self.withdrawn_at_ms:
            raise ConsentError("consent_withdrawn")
        if proxy_selection and not self.scope.allow_proxy_selection:
            raise ConsentError("proxy_selection_not_consented")
        if cloud_synthesis and not self.scope.allow_cloud_synthesis:
            raise ConsentError("cloud_synthesis_not_consented")
        if device and self.scope.devices and device not in self.scope.devices:
            raise ConsentError("device_not_consented")

    # -- persistence -----------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "consent_id": self.consent_id,
            "person": self.person,
            "granted_by": self.granted_by,
            "terms": list(self.terms),
            "scope": self.scope.to_dict(),
            "recording_path": self.recording_path,
            "recording_sha256": self.recording_sha256,
            "granted_at_ms": self.granted_at_ms,
            "withdrawn_at_ms": self.withdrawn_at_ms,
            "withdrawal_propagated": self.withdrawal_propagated,
            "note": self.note,
        }

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
            # A consent record that cannot be read is not consent. Failing closed is the
            # only safe direction.
            return None
        known = {f for f in cls.__slots__ if not f.startswith("_")}
        return cls(**{k: v for k, v in data.items() if k in known})
