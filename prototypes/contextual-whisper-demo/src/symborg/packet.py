from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal
import json
import time

PacketType = Literal["anchor", "question", "counterpoint", "source", "sentence", "memory"]
Delivery = Literal["screen", "audio_whisper", "ar", "haptic", "assistive"]
InterruptRisk = Literal["low", "medium", "high"]
ExpectedUse = Literal["think", "ask", "say", "choose", "verify"]


@dataclass(slots=True)
class CognitivePacket:
    """A compact, timely cue intended for human attention.

    The packet is not a final answer. It is a small thought seed that can be
    delivered through screen, audio, AR, haptic, or assistive channels.
    """

    packet_type: PacketType
    cue: str
    confidence: float
    topic: str = "unknown"
    depth: int = 1
    delivery: Delivery = "screen"
    interruption_risk: InterruptRisk = "low"
    cognitive_load: int = 2
    expected_use: ExpectedUse = "think"
    source_basis: list[str] = field(default_factory=list)
    supporting_context: list[str] = field(default_factory=list)
    created_at_ms: int = 0

    def __post_init__(self) -> None:
        if self.created_at_ms == 0:
            self.created_at_ms = int(time.time() * 1000)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.depth = max(0, min(5, int(self.depth)))
        self.cognitive_load = max(1, min(5, int(self.cognitive_load)))
        self.cue = " ".join(self.cue.split())

    @property
    def word_count(self) -> int:
        return len([w for w in self.cue.split() if w.strip()])

    def validation_warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.cue:
            warnings.append("empty_cue")
        if self.confidence < 0.45:
            warnings.append("low_confidence")
        if self.delivery == "audio_whisper" and self.word_count > 18:
            warnings.append("audio_cue_too_long")
        if self.delivery in {"screen", "ar"} and self.word_count > 25:
            warnings.append("visual_cue_too_long")
        if self.cognitive_load > 3 and self.delivery in {"audio_whisper", "ar"}:
            warnings.append("high_load_for_live_delivery")
        if self.interruption_risk == "high":
            warnings.append("high_interruption_risk")
        return warnings

    def to_dict(self) -> dict:
        data = asdict(self)
        data["word_count"] = self.word_count
        data["warnings"] = self.validation_warnings()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
