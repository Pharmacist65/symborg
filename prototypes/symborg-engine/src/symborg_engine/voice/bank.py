"""A person's banked voice.

Recorded while they can still speak, used after they cannot. The bank holds the
recordings, the consent record, and whatever identifier a synthesis provider issues —
and it is deliberately provider-agnostic, because which service does the cloning is a
choice that will change and the person's recordings should outlive it.

Everything lives in one directory the person owns:

    voice/
      consent.json      what they agreed to, and when
      script.json       which prompts they have read
      clips/            the recordings themselves
      provider.json     the identifier issued by whoever synthesises

They can read it, copy it, and delete it without this software. That is not a courtesy;
a voice someone can be locked out of is not really theirs.
"""

from __future__ import annotations

import json
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..providers.base import VoiceRef
from .consent import Consent, ConsentError, ConsentScope

__all__ = ["VoiceBank", "ENROLMENT_SCRIPT", "MIN_CLIP_SECONDS", "TARGET_SECONDS",
           "SPEECH_TARGET_SECONDS"]

SPEECH_TARGET_SECONDS = 2_700.0
"""Connected speech to collect beyond the script, in seconds — 45 minutes.

Cloning services state much lower minimums, but their floor is not the number that
matters. Quality rises well past it, and this recording happens once, while the person
can still give it. Under-collecting is not recoverable later."""

SAMPLE_RATE = 24_000
MIN_CLIP_SECONDS = 2.0
TARGET_SECONDS = 180.0
"""How much audio to aim for. Providers differ, and more is generally better, but the
number that matters is not the provider's minimum — it is how much someone who tires
easily can realistically give in one sitting."""

ENROLMENT_SCRIPT: tuple[str, ...] = (
    # Ordinary sentences first: if someone stops after five minutes, these are the ones
    # they will actually need, and the ones their family will most want to hear.
    "Merhaba, seni görmek çok güzel.",
    "Evet, lütfen.",
    "Hayır, teşekkür ederim.",
    "Biraz bekler misin?",
    "Şu an konuşmak istemiyorum.",
    "Seni seviyorum.",
    "İyiyim, merak etme.",
    "Canım biraz sıkkın bugün.",
    "Ağrım var, biraz yardım eder misin?",
    "Pozisyonumu değiştirebilir miyiz?",
    "Su içmek istiyorum.",
    "Doktoru çağırır mısın?",
    "Anlamadım, tekrar söyler misin?",
    "Kastettiğim bu değildi.",
    "Bunu düşünmem lazım.",
    # Then longer material, which cloning quality benefits from.
    "Bugün hava güzel görünüyor, biraz dışarı çıkmak iyi gelebilir.",
    "Dün gece iyi uyuyamadım ama sabaha doğru biraz dinlenebildim.",
    "Sana anlatmak istediğim bir şey var, acele etmeden konuşalım.",
    "Çocukken bu şarkıyı duyduğumda hep aynı şeyi düşünürdüm.",
    "Ne zaman hazır olursan başlayabiliriz, benim için sorun değil.",
)
"""What to read, in the order that matters.

The everyday phrases come first on purpose. Enrolment is tiring, and someone may stop
early — so the sentences most needed later are captured first, not last."""


@dataclass(slots=True)
class Clip:
    """One recording and the line it was read from."""

    index: int
    text: str
    path: str
    seconds: float

    def to_dict(self) -> dict:
        return {"index": self.index, "text": self.text,
                "path": self.path, "seconds": round(self.seconds, 2)}


@dataclass(slots=True)
class VoiceBank:
    """A person's recordings, their consent, and the voice it produces."""

    root: Path
    consent: Consent | None = None
    clips: list[Clip] = field(default_factory=list)
    provider: dict = field(default_factory=dict)

    # -- opening ---------------------------------------------------------------

    @classmethod
    def open(cls, root: str | Path) -> "VoiceBank":
        """Open a bank, loading whatever is already there."""
        base = Path(root)
        bank = cls(root=base)
        bank.consent = Consent.load(base / "consent.json")
        script = base / "script.json"
        if script.exists():
            try:
                bank.clips = [Clip(**c) for c in json.loads(script.read_text(encoding="utf-8"))]
            except (json.JSONDecodeError, OSError, TypeError):
                bank.clips = []
        prov = base / "provider.json"
        if prov.exists():
            try:
                bank.provider = json.loads(prov.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                bank.provider = {}
        return bank

    # -- consent ---------------------------------------------------------------

    def grant_consent(self, person: str, note: str = "",
                      recording: str | Path | None = None,
                      scope: ConsentScope | None = None,
                      granted_by: str = "") -> Consent:
        """Record that this person agreed their voice may be reproduced.

        Must happen before any recording is kept: consent obtained afterwards is not
        consent to audio that already exists.

        Args:
            recording: The person reading the terms aloud. Strongly recommended — a
                tick box cannot be verified once they can no longer confirm it.
            granted_by: A named proxy, when the person can no longer consent
                themselves. Left empty for self-consent, which is the stronger form.
        """
        if not person.strip():
            raise ConsentError("no_person_named")
        self.consent = Consent(
            person=person.strip(), note=note, granted_by=granted_by.strip(),
            scope=scope or ConsentScope(),
        )
        if recording is not None:
            self.consent.attach_recording(recording)
        self.consent.save(self.root / "consent.json")
        return self.consent

    def withdraw_consent(self, delete_remote: "Callable[[str, str], bool] | None" = None) -> dict:
        """Revoke consent, delete the recordings, and remove the remote voice.

        Withdrawal that stops at this machine is not withdrawal. The recordings go, but
        so must the trained voice wherever it lives — otherwise "delete my voice"
        deletes nothing that matters.

        Args:
            delete_remote: Called with ``(provider, voice_id)`` to remove the voice at
                the service that holds it. Should return True on success. If it is not
                supplied, or it fails, the record says so rather than claiming a
                deletion that did not happen.

        Returns:
            What was actually done, so a caller can tell the person the truth.
        """
        outcome = {"local_clips_deleted": 0, "remote_provider": "",
                   "remote_deleted": False, "remote_error": ""}

        if self.consent is not None:
            self.consent.withdraw()

        provider = self.provider.get("provider", "")
        voice_id = self.provider.get("voice_id", "")
        if provider and voice_id:
            outcome["remote_provider"] = provider
            if delete_remote is None:
                outcome["remote_error"] = "no_deletion_handler"
            else:
                try:
                    outcome["remote_deleted"] = bool(delete_remote(provider, voice_id))
                    if not outcome["remote_deleted"]:
                        outcome["remote_error"] = "provider_refused"
                except Exception as exc:
                    outcome["remote_error"] = f"{type(exc).__name__}: {exc}"

        for clip in self.clips:
            Path(clip.path).unlink(missing_ok=True)
            outcome["local_clips_deleted"] += 1
        self.clips = []
        self._save_script()
        (self.root / "provider.json").unlink(missing_ok=True)
        self.provider = {}

        if self.consent is not None:
            # Only claim propagation when there was nothing remote, or it really went.
            self.consent.withdrawal_propagated = (
                not outcome["remote_provider"] or outcome["remote_deleted"]
            )
            self.consent.save(self.root / "consent.json")
        return outcome

    def require_consent(self) -> Consent:
        if self.consent is None:
            raise ConsentError("no_consent_record")
        self.consent.require_valid()
        return self.consent

    # -- recording -------------------------------------------------------------

    def add_clip(self, index: int, audio: bytes, sample_rate: int = SAMPLE_RATE) -> Clip:
        """Store one recording. Refuses without valid consent."""
        self.require_consent()
        if index < 0 or index >= len(ENROLMENT_SCRIPT):
            raise IndexError("no_such_prompt")

        seconds = len(audio) / 2 / sample_rate
        if seconds < MIN_CLIP_SECONDS:
            raise ValueError(f"clip_too_short: {seconds:.1f}s")

        clips_dir = self.root / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        path = clips_dir / f"{index:02d}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(audio)

        clip = Clip(index=index, text=ENROLMENT_SCRIPT[index],
                    path=str(path), seconds=seconds)
        self.clips = [c for c in self.clips if c.index != index] + [clip]
        self.clips.sort(key=lambda c: c.index)
        self._save_script()
        return clip

    def _save_script(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "script.json").write_text(
            json.dumps([c.to_dict() for c in self.clips], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # -- progress --------------------------------------------------------------

    @property
    def recorded_seconds(self) -> float:
        return sum(c.seconds for c in self.clips)

    @property
    def next_prompt(self) -> tuple[int, str] | None:
        """The next line to read, or None when the script is finished."""
        done = {c.index for c in self.clips}
        for i, text in enumerate(ENROLMENT_SCRIPT):
            if i not in done:
                return i, text
        return None

    def progress(self) -> dict:
        return {
            "person": self.consent.person if self.consent else "",
            "consented": bool(self.consent and self.consent.is_valid),
            "clips": len(self.clips),
            "prompts": len(ENROLMENT_SCRIPT),
            "seconds": round(self.recorded_seconds, 1),
            "target_seconds": TARGET_SECONDS,
            "ready": self.is_ready,
        }

    @property
    def is_ready(self) -> bool:
        """Whether there is enough material to attempt cloning."""
        return (self.consent is not None and self.consent.is_valid
                and self.recorded_seconds >= 60.0)

    # -- the voice itself ------------------------------------------------------

    def attach_provider_voice(self, provider: str, voice_id: str, note: str = "") -> None:
        """Record the identifier a synthesis provider issued for this voice."""
        self.require_consent()
        self.provider = {"provider": provider, "voice_id": voice_id,
                         "note": note, "attached_at_ms": int(time.time() * 1000)}
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "provider.json").write_text(
            json.dumps(self.provider, ensure_ascii=False, indent=2), encoding="utf-8")

    def voice_ref(self, *, cloud_synthesis: bool = True, device: str = "") -> VoiceRef:
        """The reference the synthesiser should use.

        Raises:
            ConsentError: if consent is missing, withdrawn, or does not cover what is
                about to happen. The check lives here rather than at the call site so
                that no path to synthesis can skip it.
        """
        if self.consent is None:
            raise ConsentError("no_consent_record")
        self.consent.require_valid(cloud_synthesis=cloud_synthesis, device=device)
        consent = self.consent
        voice_id = self.provider.get("voice_id", "")
        if not voice_id:
            raise ConsentError("no_voice_attached")
        return VoiceRef(voice_id=voice_id, label=consent.person, is_own_voice=True)
