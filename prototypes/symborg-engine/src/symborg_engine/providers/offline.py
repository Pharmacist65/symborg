"""Deterministic offline providers.

These ship in the box so the engine always runs: no API key, no network, no optional
dependency. They exist for three reasons — hermetic tests, a demo a contributor can run
in the first minute, and a safe degradation path when a configured provider is
unavailable. They are intentionally simple and make no attempt to be clever.
"""

from __future__ import annotations

import hashlib
import json
import re

from .base import Prompt, TranscriptChunk, Utterance, VoiceRef

__all__ = ["OfflineTranscriber", "OfflineLanguageModel", "OfflineSynthesiser"]

_QUESTION_MARKERS = ("mi", "mı", "mu", "mü", "?")

_NEED_TEMPLATES: tuple[str, ...] = (
    "Evet, biraz rahatsızım.",
    "Hayır, şu an iyiyim.",
    "Bir dakika, düşünmek istiyorum.",
)

_REPAIR = "Bunların hiçbiri değil, tekrar dener misin?"


class OfflineTranscriber:
    """Returns a fixed chunk. Real recognition needs a real provider."""

    def transcribe(self, audio: bytes) -> TranscriptChunk:
        digest = hashlib.sha256(audio).hexdigest()[:8] if audio else "empty"
        return TranscriptChunk(text=f"[offline:{digest}]", speaker="partner", is_final=True)


class OfflineLanguageModel:
    """Produces plausible, deterministic candidates without a model.

    Same input always yields the same output, which is what makes tests meaningful.
    The output is a JSON array so it exercises exactly the same parsing path a real
    model's response does — the offline path must not be a special case in the engine.
    """

    def complete(self, prompt: Prompt) -> str:
        question = self._last_partner_line(prompt.user)
        candidates = self._candidates_for(question)
        return json.dumps(
            [{"text": t, "kind": k, "confidence": c} for t, k, c in candidates],
            ensure_ascii=False,
        )

    @staticmethod
    def _last_partner_line(user_prompt: str) -> str:
        lines = [ln.strip() for ln in user_prompt.splitlines() if ln.strip()]
        for line in reversed(lines):
            if line.lower().startswith(("partner:", "karşı taraf:", "muhatap:")):
                return line.split(":", 1)[1].strip()
        return lines[-1] if lines else ""

    def _candidates_for(self, question: str) -> list[tuple[str, str, float]]:
        lowered = question.lower()
        is_question = any(m in lowered.split() or lowered.endswith(m) for m in _QUESTION_MARKERS)
        out: list[tuple[str, str, float]] = []
        if is_question:
            out.append((_NEED_TEMPLATES[0], "reply", 0.55))
            out.append((_NEED_TEMPLATES[1], "reply", 0.5))
        else:
            out.append((_NEED_TEMPLATES[2], "reply", 0.45))
            out.append(("Seni dinliyorum, devam et.", "social", 0.45))
        out.append((_REPAIR, "repair", 0.4))
        return out


class OfflineSynthesiser:
    """Emits a valid, silent WAV of the right shape.

    Playable and inspectable, so the audio path can be tested end to end without a
    speech service. It is deliberately silent: a fake voice reading a real sentence is
    a demo waiting to be mistaken for a product.
    """

    _SAMPLE_RATE = 16_000

    def synthesise(self, text: str, voice: VoiceRef) -> Utterance:
        words = max(1, len(re.findall(r"\w+", text)))
        frames = int(self._SAMPLE_RATE * min(10.0, words * 0.35))
        return Utterance(
            text=text,
            audio=self._silent_wav(frames),
            mime_type="audio/wav",
            voice_id=voice.voice_id,
        )

    def _silent_wav(self, frames: int) -> bytes:
        data_size = frames * 2  # 16-bit mono
        header = b"RIFF" + (36 + data_size).to_bytes(4, "little") + b"WAVE"
        header += b"fmt " + (16).to_bytes(4, "little")
        header += (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
        header += self._SAMPLE_RATE.to_bytes(4, "little")
        header += (self._SAMPLE_RATE * 2).to_bytes(4, "little")
        header += (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
        header += b"data" + data_size.to_bytes(4, "little")
        return header + b"\x00" * data_size
