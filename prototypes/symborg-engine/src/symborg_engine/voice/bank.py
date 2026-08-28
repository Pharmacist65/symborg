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

from ..providers.base import VoiceRef
from .consent import Consent, ConsentError

__all__ = ["VoiceBank", "ENROLMENT_SCRIPT", "MIN_CLIP_SECONDS", "TARGET_SECONDS"]

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

    def grant_consent(self, person: str, note: str = "") -> Consent:
        """Record that this person agreed their voice may be reproduced.

        Must happen before any recording is kept. Consent obtained after the fact is
        not consent to the recording that already exists.
        """
        if not person.strip():
            raise ConsentError("no_person_named")
        self.consent = Consent(person=person.strip(), note=note)
        self.consent.save(self.root / "consent.json")
        return self.consent

    def withdraw_consent(self) -> None:
        """Revoke consent and delete the recordings.

        Withdrawal that leaves the audio on disk is not withdrawal.
        """
        if self.consent is not None:
            self.consent.withdraw()
            self.consent.save(self.root / "consent.json")
        for clip in self.clips:
            Path(clip.path).unlink(missing_ok=True)
        self.clips = []
        self._save_script()
        (self.root / "provider.json").unlink(missing_ok=True)
        self.provider = {}

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

    def voice_ref(self) -> VoiceRef:
        """The reference the synthesiser should use.

        Raises:
            ConsentError: if consent is missing or withdrawn. The check lives here
                rather than at the call site so that no path to synthesis can skip it.
        """
        consent = self.require_consent()
        voice_id = self.provider.get("voice_id", "")
        if not voice_id:
            raise ConsentError("no_voice_attached")
        return VoiceRef(voice_id=voice_id, label=consent.person, is_own_voice=True)
